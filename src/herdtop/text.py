"""Text measured in terminal columns, not in characters."""

import unicodedata


def char_width(char: str) -> int:
    if unicodedata.combining(char) or unicodedata.category(char) in ("Cf", "Mn"):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def width(text: str) -> int:
    return sum(char_width(c) for c in text)


def cut(text: str, size: int) -> str:
    """The text cut to `size` columns, with `…` where it was cut."""
    if width(text) <= size:
        return text
    if size <= 0:
        return ""
    kept, used = [], 0
    for char in text:
        w = char_width(char)
        if used + w > size - 1:
            break
        kept.append(char)
        used += w
    return "".join(kept) + "…"


def cut_left(text: str, size: int) -> str:
    """The text cut to `size` columns from the left, so the end stays."""
    if width(text) <= size:
        return text
    return cut(text[::-1], size)[::-1]


def pad(text: str, size: int) -> str:
    text = cut(text, size)
    return text + " " * (size - width(text))


def rpad(text: str, size: int) -> str:
    text = cut(text, size)
    return " " * (size - width(text)) + text


def one_line(text: str) -> str:
    return " ".join(text.split())
