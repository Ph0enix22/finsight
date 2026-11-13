from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.models.enums import ChatRole


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    role: ChatRole
    content: str
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    cited_txn_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
