import os
import glob
import uuid
import shutil
import asyncio
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from app.models.job import Job
from app.config.database import AsyncSessionLocal
from app.services.media_analyzer import analyze_media
from app.services.converter import convert_audio
from app.services.url_processor import analyze_url

router = APIRouter()

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    
    file_extension = os.path.splitext(file.filename)[1] if file.filename else ".mp4"
    safe_filename = f"{job_id}{file_extension}"
    file_path = os.path.join(TEMP_DIR, safe_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        media_info = analyze_media(file_path)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"Media analysis error: {str(e)}")
        
    async with AsyncSessionLocal() as db:
        new_job = Job(
            job_id=job_id,
            status="pending",
            input_type="upload",
            input_filename=file.filename,
            duration=media_info.get("duration"),
            source_codec=media_info.get("audio_codec"),
            source_bitrate=media_info.get("audio_bitrate")
        )
        db.add(new_job)
        await db.commit()
        
    return {
        "job_id": job_id,
        "status": "pending",
        "media_info": media_info
    }

async def process_job_task(job_id: str, output_format: str, bitrate: str = None):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            return
        is_url = job.input_type == "url"
        source_url = job.source_url
        input_filename = job.input_filename
    
    output_path = os.path.join(TEMP_DIR, f"{job_id}_out.{output_format}")
    input_path = None
    
    if is_url:
        import yt_dlp
        # Download template
        download_template = os.path.join(TEMP_DIR, f"{job_id}_src.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': download_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'overwrites': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android']
                }
            }
        }
        
        try:
            # Run blocking yt-dlp in thread pool
            loop = asyncio.get_running_loop()
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([source_url])
            await loop.run_in_executor(None, _download)
            
            # Find the downloaded file
            matches = glob.glob(os.path.join(TEMP_DIR, f"{job_id}_src.*"))
            if matches:
                input_path = matches[0]
            else:
                raise FileNotFoundError("Could not locate downloaded audio stream.")
        except Exception as e:
            async with AsyncSessionLocal() as db:
                job = await db.get(Job, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = f"Download failed: {str(e)}"
                    await db.commit()
            return
    else:
        # Find uploaded file
        matches = glob.glob(os.path.join(TEMP_DIR, f"{job_id}.*"))
        if matches:
            input_path = matches[0]
        else:
            # Fallback mp4
            input_path = os.path.join(TEMP_DIR, f"{job_id}.mp4")

    if not input_path or not os.path.exists(input_path):
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_message = "Source video file not found."
                await db.commit()
        return

    # Execute conversion
    try:
        await convert_audio(job_id, input_path, output_path, output_format, bitrate)
    except Exception as e:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                await db.commit()

@router.post("/convert")
async def convert_job(job_id: str, format: str, bitrate: str = None, background_tasks: BackgroundTasks = None):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job.output_format = format
        job.output_bitrate = bitrate
        job.status = "analyzing"
        job.progress = 10
        await db.commit()
        
    if background_tasks:
        background_tasks.add_task(process_job_task, job_id, format, bitrate)
        
    return {"job_id": job_id, "status": "processing"}

@router.post("/analyze")
async def analyze_url_endpoint(url: str):
    try:
        # Run analyze_url in thread pool to prevent blocking event loop
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, analyze_url, url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        new_job = Job(
            job_id=job_id,
            status="pending",
            input_type="url",
            source_url=url,
            input_filename=info.get("title"),
            duration=info.get("duration"),
            source_codec=info.get("audio_codec"),
            source_bitrate=info.get("audio_bitrate")
        )
        db.add(new_job)
        await db.commit()
        
    return {
        "job_id": job_id,
        "status": "pending",
        "media_info": info
    }

@router.get("/job/{job_id}")
async def get_job_status(job_id: str):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "error_message": job.error_message,
            "output_format": job.output_format
        }

@router.get("/download/{job_id}")
async def download_job(job_id: str):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "completed":
            raise HTTPException(status_code=400, detail=f"Job is not completed yet (status: {job.status})")
            
        custom_name = job.input_filename or f"Audivault_{job_id}"
        clean_name = "".join(c for c in custom_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not clean_name:
            clean_name = f"Audivault_{job_id}"
            
    matches = glob.glob(os.path.join(TEMP_DIR, f"{job_id}_out.*"))
    if matches:
        file_path = matches[0]
        ext = os.path.splitext(file_path)[1].lower()
        
        media_types = {
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
        }
        media_type = media_types.get(ext, "application/octet-stream")
        download_filename = f"{clean_name}{ext}"
        
        return FileResponse(
            file_path, 
            media_type=media_type, 
            filename=download_filename,
            headers={
                "Content-Disposition": f'attachment; filename="{download_filename}"'
            }
        )
            
    raise HTTPException(status_code=404, detail="Output file not found")
