from enum import Enum


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def z_score_threshold(self) -> float:
        if self == Sensitivity.LOW:
            return 3.0
        if self == Sensitivity.MEDIUM:
            return 2.0
        return 1.5

    @property
    def distribution_distance_threshold(self) -> float:
        if self == Sensitivity.LOW:
            return 0.45
        if self == Sensitivity.MEDIUM:
            return 0.30
        return 0.20
