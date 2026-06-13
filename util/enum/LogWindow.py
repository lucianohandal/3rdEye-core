from datetime import timedelta
from enum import Enum


class LogWindow(str, Enum):
    xs = "xs"
    s = "s"
    m = "m"
    l = "l"
    xl = "xl"
    xxl = "xxl"

    @property
    def duration(self) -> timedelta:
        if self == LogWindow.xs:
            return timedelta(minutes=1)
        if self == LogWindow.s:
            return timedelta(minutes=5)
        if self == LogWindow.m:
            return timedelta(minutes=30)
        if self == LogWindow.l:
            return timedelta(hours=3)
        if self == LogWindow.xl:
            return timedelta(days=1)
        return timedelta(weeks=4)
