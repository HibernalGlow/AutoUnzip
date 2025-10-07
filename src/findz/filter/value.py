"""Value types for filter expressions."""

from typing import Optional


class Value:
    """Represents a value that can be a number, text, or boolean."""
    
    def __init__(
        self,
        number: Optional[int] = None,
        text: Optional[str] = None,
        boolean: Optional[bool] = None
    ):
        self.number = number
        self.text = text
        self.boolean = boolean
    
    def __str__(self) -> str:
        """Return string representation of the value."""
        if self.number is not None:
            return str(self.number)
        elif self.text is not None:
            return self.text
        elif self.boolean is not None:
            return str(self.boolean)
        return ""
    
    def to_bool(self) -> bool:
        """Convert value to boolean."""
        if self.number is not None:
            return self.number != 0
        elif self.text is not None:
            return self.text != ""
        elif self.boolean is not None:
            return self.boolean
        return False


def number_value(n: int) -> Value:
    """Create a Value instance representing a number."""
    return Value(number=n)


def text_value(s: str) -> Value:
    """Create a Value instance representing text."""
    return Value(text=s)


def bool_value(b: bool) -> Value:
    """Create a Value instance representing a boolean."""
    return Value(boolean=b)
