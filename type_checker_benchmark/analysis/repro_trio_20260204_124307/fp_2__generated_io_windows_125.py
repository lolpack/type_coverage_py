"""Repro for pyrefly false positive with platform-conditional type aliases.

Pyrefly resolves platform-conditional type aliases using the host platform,
then errors when code intended for a different platform uses platform-specific
attributes. Pyright correctly handles this.
"""
from typing import TYPE_CHECKING


class WindowsIOManager:
    """Windows-only IO manager with Windows-specific methods."""
    def register_with_iocp(self, handle: int) -> None:
        pass


class KqueueIOManager:
    """macOS/BSD IO manager - does NOT have register_with_iocp."""
    def wait_kevent(self, fd: int) -> None:
        pass


# Platform-conditional type alias - on TYPE_CHECKING (static analysis),
# this will use KqueueIOManager on non-Windows platforms
if TYPE_CHECKING:
    # Simulates: elif TYPE_CHECKING or hasattr(select, "kqueue"):
    TheIOManager = KqueueIOManager
else:
    TheIOManager = WindowsIOManager


class Runner:
    io_manager: TheIOManager


class RunContext:
    runner: Runner


GLOBAL_RUN_CONTEXT = RunContext()


def register_with_iocp(handle: int) -> None:
    """Windows-specific function that calls io_manager.register_with_iocp.

    Pyrefly sees TheIOManager as KqueueIOManager (from TYPE_CHECKING branch)
    and reports that KqueueIOManager has no attribute 'register_with_iocp'.
    Pyright correctly allows this code.
    """
    # Pyrefly error: Object of class `KqueueIOManager` has no attribute `register_with_iocp`
    return GLOBAL_RUN_CONTEXT.runner.io_manager.register_with_iocp(handle)
