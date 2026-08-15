import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Create local sqlite db for dev
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
os.makedirs(DB_DIR, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DB_DIR}/audivault.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

async def init_db():
    from app.models.job import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
