import os
import asyncio
import subprocess
from typing import Optional
from app.models.job import Job
from app.config.database import AsyncSessionLocal

def _run_ffmpeg(cmd: list) -> tuple[int, str]:
    """Runs ffmpeg synchronously in thread pool."""
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False
        )
        return res.returncode, res.stderr or ""
    except Exception as e:
        return 1, str(e)

async def convert_audio(
    job_id: str,
    input_path: str,
    output_path: str,
    target_format: str,
    target_bitrate: Optional[str] = None
):
    """
    Runs FFmpeg to extract and convert audio.
    Updates the database with progress and final status.
    """
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn"  # no video stream
    ]
    
    if target_format == "mp3":
        cmd.extend(["-c:a", "libmp3lame"])
        if target_bitrate:
            cmd.extend(["-b:a", target_bitrate])
        else:
            cmd.extend(["-b:a", "320k"])
    elif target_format == "m4a":
        cmd.extend(["-c:a", "aac"])
        if target_bitrate:
            cmd.extend(["-b:a", target_bitrate])
        else:
            cmd.extend(["-b:a", "256k"])
    elif target_format == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    elif target_format == "flac":
        cmd.extend(["-c:a", "flac"])
    else:
        cmd.extend(["-c:a", "copy"])
        
    cmd.append(output_path)
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if job:
            job.status = "encoding"
            job.progress = 50
            await db.commit()
            
    # Run ffmpeg synchronously inside thread pool to prevent Windows event loop subprocess issues
    loop = asyncio.get_running_loop()
    returncode, stderr_output = await loop.run_in_executor(None, _run_ffmpeg, cmd)
    
    if returncode != 0 or not os.path.exists(output_path):
        error_msg = stderr_output or "Unknown FFmpeg error or output file not created"
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_message = f"FFmpeg error: {error_msg[:300]}"
                await db.commit()
        raise Exception(f"FFmpeg conversion failed: {error_msg[:200]}")
    
    from datetime import datetime, timezone
    from app.services.cleanup import schedule_delayed_cleanup

    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if job:
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            
    # Automatically schedule deletion of files and DB entry 5 minutes (300s) after completion
    asyncio.create_task(schedule_delayed_cleanup(job_id, delay_seconds=300))
            
    return True
