"""Minimal repro for pyrefly false positive with variadic generics unpacking.

Pyrefly reports an error when passing arguments through nested variadic
generic functions, while pyright correctly accepts this code.
"""
from typing import Awaitable, Callable, TypeVar
from typing_extensions import TypeVarTuple, Unpack

T = TypeVar("T")
Ts = TypeVarTuple("Ts")
PosArgT = TypeVarTuple("PosArgT")
RetT = TypeVar("RetT")


class MemoryReceiveChannel:
    pass


class MemorySendChannel:
    pass


class Nursery:
    def start_soon(
        self,
        async_fn: Callable[[Unpack[PosArgT]], Awaitable[object]],
        *args: Unpack[PosArgT],
    ) -> None:
        ...


async def run_sync(
    sync_fn: Callable[[Unpack[Ts]], RetT],
    *args: Unpack[Ts],
) -> RetT:
    ...


def thread_fn(receive_from_trio: MemoryReceiveChannel, send_to_trio: MemorySendChannel) -> None:
    pass


async def main() -> None:
    nursery = Nursery()
    receive_from_trio = MemoryReceiveChannel()
    send_to_trio = MemorySendChannel()

    # This line triggers pyrefly error but should pass pyright
    nursery.start_soon(run_sync, thread_fn, receive_from_trio, send_to_trio)
