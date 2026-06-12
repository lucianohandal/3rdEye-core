from enum import Enum
from datetime import timedelta

class LogWindow(Enum):
    xs = timedelta(minutes=1)
    s = timedelta(minutes=5)
    m = timedelta(minutes=30)
    l = timedelta(hours=3)
    xl = timedelta(days=1)
    xxl = timedelta(weeks=4)