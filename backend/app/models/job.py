from sqlalchemy import Column, String, Integer, DateTime, Float
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True, index=True)
    status = Column(String, default="pending")  # pending, analyzing, extracting, encoding, completed, failed
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    
    input_type = Column(String)  # upload, url
    source_url = Column(String, nullable=True)
    input_filename = Column(String, nullable=True)
    input_size = Column(Integer, nullable=True)
    
    output_format = Column(String, nullable=True)
    output_size = Column(Integer, nullable=True)
    
    duration = Column(Float, nullable=True)
    
    source_codec = Column(String, nullable=True)
    source_bitrate = Column(String, nullable=True)
    output_bitrate = Column(String, nullable=True)
    
    progress = Column(Integer, default=0)
    error_message = Column(String, nullable=True)
