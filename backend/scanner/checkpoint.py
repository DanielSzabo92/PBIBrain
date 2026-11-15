"""A cancellation point the long scan steps call without knowing who started them.

The project scan sets ``CHECKPOINT`` to a function that raises when the user cancelled;
formula analysis and the graph builder call ``checkpoint()`` per expression and between
their stages, so a cancel takes effect in a second or two instead of after the whole step.
Outside a project scan nothing is set and ``checkpoint()`` costs one lookup.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

CHECKPOINT: ContextVar[Callable[[], None] | None] = ContextVar("scan_checkpoint", default=None)


def checkpoint() -> None:
    check = CHECKPOINT.get()
    if check is not None:
        check()


@contextmanager
def checkpoints(check: Callable[[], None] | None) -> Iterator[None]:
    token = CHECKPOINT.set(check)
    try:
        yield
    finally:
        CHECKPOINT.reset(token)
