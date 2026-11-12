"""Name tokenizer and letter case styles (technical design section 5).

``tokenize`` splits a name at separators and at case changes. ``words`` keeps
the separator parts as they are and splits at case changes only when the name
has no separator. The letter case checks and the render functions use one
fixed list of styles.
"""

from __future__ import annotations

SEPARATOR_CHARS = (" ", "_", "-")
SEPARATOR_VALUES = {"space": " ", "underscore": "_", "none": ""}
SEPARATORS = ("space", "underscore", "none")
CASE_STYLES = ("title", "pascal", "camel", "snake", "upper", "lower")
CASE_TEXT = {
    "title": "Title Case",
    "pascal": "PascalCase",
    "camel": "camelCase",
    "snake": "snake_case",
    "upper": "UPPER",
    "lower": "lower",
}


def _kind(char: str) -> str:
    if char.isupper():
        return "upper"
    if char.isalpha():
        return "lower"
    if char.isdigit():
        return "digit"
    return "symbol"


def _split_case(chunk: str) -> list[str]:
    """Split one chunk with no separator at case changes, letter and digit changes, and symbols."""

    tokens: list[str] = []
    current = ""
    for index, char in enumerate(chunk):
        if not current:
            current = char
            continue
        before = _kind(current[-1])
        kind = _kind(char)
        following = _kind(chunk[index + 1]) if index + 1 < len(chunk) else None
        split = False
        if kind == "upper" and before == "lower" or kind == "upper" and before == "upper" and following == "lower" or {kind, before} & {"digit", "symbol"} and kind != before:
            split = True
        if split:
            tokens.append(current)
            current = char
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def separator_chunks(name: str) -> list[str]:
    """Split a name at the separator characters. Empty parts are dropped."""

    chunks = [name]
    for separator in SEPARATOR_CHARS:
        chunks = [part for chunk in chunks for part in chunk.split(separator)]
    return [chunk for chunk in chunks if chunk]


def tokenize(name: str) -> list[str]:
    """Split a name at separators and at case changes."""

    return [token for chunk in separator_chunks(name) for token in _split_case(chunk)]


def used_separators(name: str) -> set[str]:
    return {char for char in SEPARATOR_CHARS if char in name.strip()}


def words(name: str) -> list[str]:
    """The words of a name: the separator parts, or the case tokens of a name with no separator."""

    if used_separators(name):
        return separator_chunks(name)
    return _split_case(name)


def main_separator(name: str) -> str:
    """The separator value that the name uses most. A name with no separator gives "none"."""

    counts = {key: name.count(value) for key, value in SEPARATOR_VALUES.items() if value}
    best = max(counts, key=lambda key: (counts[key], -SEPARATORS.index(key)))
    return best if counts[best] else "none"


def _cased(text: str) -> list[str]:
    return [char for char in text if char.isalpha() and (char.isupper() or char.islower())]


def is_case(name: str, style: str) -> bool:
    """Give True when the name obeys the letter case style."""

    letters = _cased(name)
    if not letters:
        return False
    separators = used_separators(name)
    if style == "upper":
        return all(char.isupper() for char in letters)
    if style == "lower":
        return all(char.islower() for char in letters)
    if style == "snake":
        return separators <= {"_"} and all(char.islower() for char in letters) and "__" not in name \
            and not name.startswith("_") and not name.endswith("_")
    if style in {"pascal", "camel"}:
        if separators or not name[0].isalpha():
            return False
        return name[0].isupper() if style == "pascal" else name[0].islower()
    if style == "title":
        return all(not chunk[0].isalpha() or chunk[0].isupper() for chunk in separator_chunks(name))
    raise ValueError(f"Unknown letter case style: {style}")


def _capital(token: str) -> str:
    return token[:1].upper() + token[1:]


def render(parts: list[str], style: str | None, separator: str | None, original: str) -> str:
    """Join the words again with a letter case style and a separator value.

    With no style and no separator, the function gives the original name. A
    style with a fixed separator (camelCase, PascalCase, snake_case) uses it
    when no separator rule is given.
    """

    if style is None and separator is None:
        return original
    if style == "title" or style == "pascal":
        parts = [_capital(part) for part in parts]
    elif style == "camel":
        parts = [part.lower() if index == 0 else _capital(part.lower()) for index, part in enumerate(parts)]
    elif style == "snake":
        parts = [part.lower() for part in parts]
    elif style == "upper":
        parts = [part.upper() for part in parts]
    elif style == "lower":
        parts = [part.lower() for part in parts]
    if separator is None:
        if style in {"pascal", "camel"}:
            separator = "none"
        elif style == "snake":
            separator = "underscore"
        else:
            separator = main_separator(original)
            if separator == "none" and len(parts) > 1:
                separator = "space"
    return SEPARATOR_VALUES[separator].join(parts)
