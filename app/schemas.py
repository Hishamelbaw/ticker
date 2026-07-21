from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AlertCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    threshold: float
    direction: str = Field(pattern="^(above|below)$")
    expires_at: datetime
    ack_window_seconds: int = Field(default=300, gt=0)


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    threshold: float
    direction: str
    expires_at: datetime
    ack_window_seconds: int
    current_state: str
    triggered_at: datetime | None
    created_at: datetime
