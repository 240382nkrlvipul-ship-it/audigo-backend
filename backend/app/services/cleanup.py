import os
import glob
import time
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from app.models.job import Job
from app.config.database import AsyncSessionLocal

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp")

async def delete_job_files(job_id: str):
    """Deletes all temporary source and output files associated with a job_id."""
    patterns = [
        os.path.join(TEMP_DIR, f"{job_id}.*"),
        os.path.join(TEMP_DIR, f"{job_id}_*"),
    ]
    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"[Cleanup] Deleted temporary file: {file_path}")
            except Exception as e:
                print(f"[Cleanup] Error deleting file {file_path}: {e}")

async def purge_job(job_id: str):
    """Deletes the job's files and its record from the database."""
    await delete_job_files(job_id)
    try:
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            if job:
                await db.delete(job)
                await db.commit()
                print(f"[Cleanup] Purged job {job_id} from database.")
    except Exception as e:
        print(f"[Cleanup] Error purging job {job_id} from DB: {e}")

async def schedule_delayed_cleanup(job_id: str, delay_seconds: int = 300):
    """
    Waits for `delay_seconds` (default 5 minutes) then completely erases the converted audio and DB record.
    """
    try:
        await asyncio.sleep(delay_seconds)
        await purge_job(job_id)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[Cleanup] Delayed cleanup error for job {job_id}: {e}")

async def cleanup_old_files_and_jobs(max_age_minutes: int = 5):
    """
    Periodic background daemon that purges files and DB jobs older than max_age_minutes (5 minutes).
    Runs every 60 seconds.
    """
    while True:
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
            
            async with AsyncSessionLocal() as db:
                # Find all jobs created or completed before cutoff_time
                stmt = select(Job).where(
                    (Job.completed_at != None) & (Job.completed_at <= cutoff_time) |
                    (Job.created_at <= cutoff_time)
                )
                result = await db.execute(stmt)
                old_jobs = result.scalars().all()
                
                for job in old_jobs:
                    await delete_job_files(job.job_id)
                    await db.delete(job)
                
                if old_jobs:
                    await db.commit()
                    print(f"[Cleanup] Periodic sweep removed {len(old_jobs)} expired jobs (older than {max_age_minutes}m).")
            
            # Also clean up any unindexed orphan files in temp older than max_age_minutes
            now_ts = time.time()
            cutoff_ts = now_ts - (max_age_minutes * 60)
            for file_name in os.listdir(TEMP_DIR):
                if file_name.startswith("."):
                    continue
                file_path = os.path.join(TEMP_DIR, file_name)
                try:
                    if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff_ts:
                        os.remove(file_path)
                        print(f"[Cleanup] Removed orphaned temp file: {file_name}")
                except Exception as e:
                    print(f"[Cleanup] Error removing orphan file {file_path}: {e}")

        except Exception as e:
            print(f"[Cleanup] Periodic sweep error: {e}")
            
        # Check every 60 seconds
        await asyncio.sleep(60)
