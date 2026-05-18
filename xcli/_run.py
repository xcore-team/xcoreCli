"""Shared utilities for calling xcore handlers."""
import asyncio
from argparse import Namespace
from typing import Any, Callable, Coroutine


def ns(**kwargs) -> Namespace:
    """Build an argparse-compatible Namespace with config=None by default."""
    kwargs.setdefault("config", None)
    return Namespace(**kwargs)


def run(coro: Coroutine[Any, Any, Any]) -> None:
    asyncio.run(coro)
