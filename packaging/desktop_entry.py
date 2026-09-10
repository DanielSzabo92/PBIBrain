"""Frozen GUI entry point that retains the backend.desktop package context."""

from backend.desktop.host import run


if __name__ == "__main__":
    raise SystemExit(run())
