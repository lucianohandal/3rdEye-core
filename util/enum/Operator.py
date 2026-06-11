from enum import Enum


class Operator(str, Enum):
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="

    def compare(self, left: float, right: float) -> bool:
        if self == Operator.GREATER_THAN:
            return left > right
        if self == Operator.GREATER_THAN_OR_EQUAL:
            return left >= right
        if self == Operator.LESS_THAN:
            return left < right
        if self == Operator.LESS_THAN_OR_EQUAL:
            return left <= right
        if self == Operator.EQUAL:
            return left == right
        return left != right
