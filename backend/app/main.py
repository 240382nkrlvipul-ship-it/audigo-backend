from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.routes.api import router as api_router
from app.config.database import init_db

app = FastAPI(title="Audivault API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import asyncio
from app.services.cleanup import cleanup_old_files_and_jobs

@app.on_event("startup")
async def startup_event():
    await init_db()
    # Start auto-cleanup background task (erases files and records older than 5 minutes)
    asyncio.create_task(cleanup_old_files_and_jobs(max_age_minutes=5))

app.include_router(api_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Welcome to Audivault API"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
