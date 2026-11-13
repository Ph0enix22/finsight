from sqlmodel import SQLModel, create_engine

from app.core.config import settings

connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
