"""Text normalization of the merge compare (technical design section 4.2).

Default DAX normalization ignores whitespace, comments, the letter case of
keywords and function names, the letter case of names in references, and the
quotes on table names. It keeps a table prefix: ``[Total]`` is not equal to
``Sales[Total]``. A rename map reads donor references through the alignment
("same after rename").

M text, descriptions, and format strings are exact text. The default compare
ignores only the line ending style and the spaces at the end of lines. Strict
compare ignores only the line ending style.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from backend.dax.parser import dax_tokens


@dataclass(frozen=True)
class RenameMap:
    """Donor names to target names, from the alignment. All keys are case-folded."""

    tables: Mapping[str, str] = field(default_factory=dict)
    measures: Mapping[str, str] = field(default_factory=dict)
    columns: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.tables or self.measures or self.columns)


NO_RENAMES = RenameMap()


def line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def exact_text(text: str | None, *, strict: bool = False) -> str | None:
    """Normalize M text, a description, or a format string."""

    if text is None:
        return None
    value = line_endings(str(text))
    if strict:
        return value
    return "\n".join(line.rstrip() for line in value.split("\n"))


def _unquote_table(text: str) -> str:
    return text[1:-1].replace("''", "'") if len(text) >= 2 and text[0] == "'" else text


def dax_key(text: str | None, renames: RenameMap = NO_RENAMES) -> tuple[str, ...] | None:
    """Give the default normalization of a DAX text as a token tuple. Equal tuples mean equal DAX."""

    if text is None:
        return None
    tokens, failed = dax_tokens(str(text))
    if failed:
        # The lexer cannot read the text. Compare the text with collapsed whitespace only.
        return ("$text", " ".join(str(text).split()))
    result: list[str] = []
    table: str | None = None
    for position, token in enumerate(tokens):
        following = tokens[position + 1] if position + 1 < len(tokens) else None
        if token.kind == "TABLE_NAME" or (token.kind == "IDENTIFIER" and following is not None and following.kind == "BRACKET_IDENT"):
            name = _unquote_table(token.text)
            folded = name.casefold()
            name = renames.tables.get(folded, name)
            table = folded
            result.append("N:" + name.casefold())
            continue
        if token.kind == "BRACKET_IDENT":
            name = token.text[1:-1]
            folded = name.casefold()
            if table is not None:
                name = renames.columns.get((table, folded), name)
            else:
                name = renames.measures.get(folded, name)
            result.append("B:" + name.casefold())
            table = None
            continue
        table = None
        if token.kind in {"IDENTIFIER", "VAR", "RETURN", "IN", "NOT"}:
            result.append("N:" + token.text.casefold())
        else:
            result.append(token.text)
    return tuple(result)


def dax_equal(target: str | None, donor: str | None, *, strict: bool, renames: RenameMap = NO_RENAMES) -> tuple[bool, bool]:
    """Compare two DAX texts. Give (equal, equal only through the rename map)."""

    if strict:
        return exact_text(target, strict=True) == exact_text(donor, strict=True), False
    plain = dax_key(target) == dax_key(donor)
    if plain or not renames:
        return plain, False
    through = dax_key(target) == dax_key(donor, renames)
    return through, through
