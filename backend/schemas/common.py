"""Common API schemas and generics"""
from pydantic import BaseModel
from typing import Generic, TypeVar, List, Optional
from datetime import datetime, timezone

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standardized API error response"""
    detail: str
    status_code: Optional[int] = None
    error_type: Optional[str] = None
    timestamp: str = datetime.now(timezone.utc).isoformat()


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper"""
    items: List[T]
    total: int
    limit: int
    offset: int = 0
