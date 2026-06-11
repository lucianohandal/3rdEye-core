from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        if self == Severity.INFO:
            return 0
        if self == Severity.LOW:
            return 1
        if self == Severity.MEDIUM:
            return 2
        if self == Severity.HIGH:
            return 3
        return 4

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank
