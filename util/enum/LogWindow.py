from enum import Enum
from datetime import timedelta

class LogWindow(str, Enum):
    short = "5m"
    medium = "30m"
    long = "3h"

    @property
    def duration(self) -> timedelta:
        if self == LogWindow.short:
            return timedelta(minutes=5)
        if self == LogWindow.medium:
            return timedelta(minutes=30)
        return timedelta(hours=3)
