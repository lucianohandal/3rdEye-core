from pydantic import BaseModel, Field


class ExpectedPattern(BaseModel):
    key: str
    historical_occurrences: int = Field(default=0, ge=0)
    schedule: str | None = None
