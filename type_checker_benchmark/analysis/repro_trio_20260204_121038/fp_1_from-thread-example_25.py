"""Minimal repro for pyrefly vs pyright discrepancy with variadic generics (Unpack)."""
from typing import Awaitable, Callable, TypeVarTuple, Unpack

Ts = TypeVarTuple("Ts")
PosArgT = TypeVarTuple("PosArgT")


class MemoryReceiveChannel:
    pass


class MemorySendChannel:
    pass


def outer_fn(
    async_fn: Callable[[Unpack[PosArgT]], Awaitable[object]],
    *args: Unpack[PosArgT],
) -> None:
    pass


async def inner_fn(
    sync_fn: Callable[[Unpack[Ts]], object],
    *args: Unpack[Ts],
) -> object:
    return sync_fn(*args)


def thread_fn(receive: MemoryReceiveChannel, send: MemorySendChannel) -> None:
    pass


receive_from_trio = MemoryReceiveChannel()
send_to_trio = MemorySendChannel()

# This is the problematic call: passing a variadic generic function as first arg
# to another variadic generic function
outer_fn(inner_fn, thread_fn, receive_from_trio, send_to_trio)
