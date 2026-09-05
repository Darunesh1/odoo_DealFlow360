from typing import Generic, List, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class Message(BaseModel):
    """Generic message response used by endpoints without a resource payload."""

    message: str


class Page(BaseModel, Generic[T]):
    """Envelope returned by paginated list endpoints."""

    items: List[T]
    total: int
    page: int
    size: int
    pages: int
