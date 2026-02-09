"""Repro for pyrefly false positive with variadic generics and nested callable.

Pyrefly reports error when passing an async function with variadic type parameters
to another function with variadic type parameters via start_soon-like pattern.
Pyright correctly accepts this code.
"""
from typing import Awaitable, Callable, TypeVarTuple, Unpack

Ts = TypeVarTuple("Ts")
PosArgT = TypeVarTuple("PosArgT")


class MemoryReceiveChannel:
    pass


class MemorySendChannel:
    pass


def thread_fn(receive: MemoryReceiveChannel, send: MemorySendChannel) -> None:
    pass


async def run_sync(
    sync_fn: Callable[[Unpack[Ts]], object],
    *args: Unpack[Ts],
) -> object:
    return sync_fn(*args)


class Nursery:
    def start_soon(
        self,
        async_fn: Callable[[Unpack[PosArgT]], Awaitable[object]],
        *args: Unpack[PosArgT],
    ) -> None:
        pass


async def main() -> None:
    nursery = Nursery()
    receive_from_trio = MemoryReceiveChannel()
    send_to_trio = MemorySendChannel()

    # This should be valid: run_sync takes (sync_fn, *args) where sync_fn: (A, B) -> object
    # So start_soon receives run_sync (which is async) and args=(thread_fn, receive, send)
    # Pyrefly incorrectly reports an error here
    nursery.start_soon(
        run_sync, thread_fn, receive_from_trio, send_to_trio
    )
