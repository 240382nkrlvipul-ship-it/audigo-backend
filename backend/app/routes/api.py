import os
import glob
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

from app.models.job import Job
from app.database import AsyncSessionLocal
from app.services.media_analyzer import analyze_media
from app.services.url_processor import analyze_url, get_youtube_video_id
from app.services.converter import convert_media
from app.services.cleanup import cleanup_old_files_and_jobs

router = APIRouter()

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")
os.makedirs(TEMP_DIR, exist_ok=True)

class AnalyzeUrlRequest(BaseModel):
    url: str

class ConvertRequest(BaseModel):
    job_id: str
    output_format: str = "mp3"
    bitrate: Optional[str] = "320k"
    sample_rate: Optional[str] = "48000"
    channels: Optional[str] = "2"
    volume: Optional[float] = 1.0

async def process_conversion_task(
    job_id: str,
    output_format: str,
    bitrate: Optional[str],
    sample_rate: Optional[str],
    channels: Optional[str],
    volume: Optional[float]
):
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
        download_template = os.path.join(TEMP_DIR, f"{job_id}_src.%(ext)s")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': download_template,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'overwrites': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36'
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                    'player_skip': ['web', 'configs']
                }
            }
        }
        
        target_url = source_url.strip()
        vid = get_youtube_video_id(target_url)
        if vid:
            target_url = f"https://www.youtube.com/watch?v={vid}"
        elif not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = f"https://{target_url}"

        try:
            loop = asyncio.get_running_loop()
            def _download():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([target_url])
            await loop.run_in_executor(None, _download)
            
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
        matches = glob.glob(os.path.join(TEMP_DIR, f"{job_id}.*"))
        if matches:
            input_path = matches[0]
        else:
            input_path = os.path.join(TEMP_DIR, f"{job_id}.mp4")

    if not input_path or not os.path.exists(input_path):
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_message = "Source media file not found."
                await db.commit()
        return

    await convert_media(
        job_id=job_id,
        input_path=input_path,
        output_path=output_path,
        output_format=output_format,
        bitrate=bitrate or "320k",
        sample_rate=sample_rate or "48000",
        channels=channels or "2",
        volume=volume or 1.0
    )

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    async with AsyncSessionLocal() as db:
        job = Job(
            input_type="upload",
            input_filename=file.filename,
            file_size=file.size or 0,
            status="analyzing"
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    ext = os.path.splitext(file.filename)[1] or ".mp4"
    saved_path = os.path.join(TEMP_DIR, f"{job_id}{ext}")
    
    try:
        with open(saved_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                f.write(chunk)
                
        media_info = analyze_media(saved_path)
        
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            job.status = "analyzed"
            job.duration = media_info.get("duration")
            job.audio_codec = media_info.get("audio_codec")
            job.audio_bitrate = media_info.get("audio_bitrate")
            job.sample_rate = media_info.get("sample_rate")
            job.channels = media_info.get("channels")
            await db.commit()
            
        return {
            "job_id": job_id,
            "filename": file.filename,
            "details": media_info
        }
    except Exception as e:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_message = str(e)
                await db.commit()
        raise HTTPException(status_code=400, detail=f"Failed to process uploaded file: {str(e)}")

@router.post("/analyze")
async def analyze_online_url(req: AnalyzeUrlRequest):
    try:
        media_info = analyze_url(req.url)
        
        async with AsyncSessionLocal() as db:
            job = Job(
                input_type="url",
                source_url=req.url,
                input_filename=media_info.get("title", "Online Video"),
                duration=media_info.get("duration"),
                audio_codec=media_info.get("audio_codec"),
                audio_bitrate=media_info.get("audio_bitrate"),
                sample_rate=media_info.get("sample_rate"),
                channels=media_info.get("channels"),
                status="analyzed"
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_id = job.id
            
        return {
            "job_id": job_id,
            "url": req.url,
            "details": media_info
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/convert")
async def start_conversion(req: ConvertRequest, background_tasks: BackgroundTasks):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, req.job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job.output_format = req.output_format
        job.status = "pending"
        job.progress = 0
        await db.commit()

    background_tasks.add_task(
        process_conversion_task,
        job_id=req.job_id,
        output_format=req.output_format,
        bitrate=req.bitrate,
        sample_rate=req.sample_rate,
        channels=req.channels,
        volume=req.volume
    )
    
    return {"job_id": req.job_id, "status": "queued"}

@router.get("/progress/{job_id}")
async def get_progress(job_id: str):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "job_id": job.id,
            "status": job.status,
            "progress": job.progress,
            "error_message": job.error_message,
            "download_url": f"/api/download/{job.id}" if job.status == "completed" else None
        }

@router.get("/download/{job_id}")
async def download_converted_file(job_id: str):
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job or job.status != "completed":
            raise HTTPException(status_code=404, detail="Converted file is not ready or has expired")
        
        output_format = job.output_format or "mp3"
        filename = f"{os.path.splitext(job.input_filename or 'audio')[0]}.{output_format}"

    file_path = os.path.join(TEMP_DIR, f"{job_id}_out.{output_format}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found on server or was automatically cleaned up.")
        
    return FileResponse(
        path=file_path,
        media_type=f"audio/{output_format}",
        filename=filename
    )
