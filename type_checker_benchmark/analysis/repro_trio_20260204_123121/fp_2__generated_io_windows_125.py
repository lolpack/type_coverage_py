# Minimal repro for pyrefly/pyright discrepancy
# Original file: trio/_core/_generated_io_windows.py line 125
# Error: Object of class `KqueueIOManager` has no attribute `register_with_iocp`
#
# The issue: Platform-conditional type aliasing where TheIOManager is
# KqueueIOManager during TYPE_CHECKING on non-Windows, but the code
# expects WindowsIOManager methods. Pyrefly doesn't narrow the type
# based on the platform assertion.

import sys
from typing import TYPE_CHECKING

# On macOS during TYPE_CHECKING: TheIOManager = KqueueIOManager
# On Windows during TYPE_CHECKING: TheIOManager = WindowsIOManager
# The assertion at line 21 tries to guard this, but pyrefly may not respect it.

class KqueueIOManager:
    """macOS IO manager - does NOT have register_with_iocp"""
    def wait_readable(self) -> None: ...
    def wait_writable(self) -> None: ...

class WindowsIOManager:
    """Windows IO manager - HAS register_with_iocp"""
    def wait_readable(self) -> None: ...
    def wait_writable(self) -> None: ...
    def register_with_iocp(self, handle: int) -> None: ...

class Runner:
    io_manager: "TheIOManager"

class RunContext:
    runner: Runner

# Platform-conditional type alias (same as in trio's _run.py lines 3108-3132)
if sys.platform == "win32":
    TheIOManager = WindowsIOManager
elif TYPE_CHECKING or True:  # kqueue check simplified
    TheIOManager = KqueueIOManager

# This assertion guards that in TYPE_CHECKING, we should be on win32
# Pyright respects this, pyrefly may not
assert not TYPE_CHECKING or sys.platform == "win32"

GLOBAL_RUN_CONTEXT = RunContext()

def register_with_iocp(handle: int) -> None:
    # This line triggers the error on pyrefly but not pyright
    return GLOBAL_RUN_CONTEXT.runner.io_manager.register_with_iocp(handle)
