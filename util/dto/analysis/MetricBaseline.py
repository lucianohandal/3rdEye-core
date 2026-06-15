from pydantic import BaseModel, Field


class MetricBaseline(BaseModel):
    mean: float
    stddev: float = Field(default=0, ge=0)
    sample_count: int = Field(default=0, ge=0)
