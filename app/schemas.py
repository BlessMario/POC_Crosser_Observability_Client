from pydantic import BaseModel, Field
from typing import Any

class SessionCreate(BaseModel):
    node: str
    topic_filters: list[str] = Field(min_length=1)

class SessionOut(BaseModel):
    id: str
    state: str

class MessageOut(BaseModel):
    ts: str
    topic: str
    payload: Any
    qos: int
    retained: bool
