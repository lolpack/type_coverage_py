# CANNOT_REPRODUCE
#
# This discrepancy cannot be reproduced without external imports.
#
# Original error: pyrefly reports "Unexpected keyword argument `tasks_waiting_read`
# in function `object.__init__`" on line 224 of _io_epoll.py
#
# Root cause: The code uses `@attrs.frozen(eq=False)` decorator which generates
# an __init__ method accepting keyword arguments for class attributes.
#
# Why it cannot be reproduced without attrs:
# - Pyright has special built-in support for the attrs library via bundled type stubs
# - Pyrefly doesn't have this special handling
# - Without the actual attrs module, both type checkers treat custom decorators
#   identically (neither understands dynamic class transformation)
#
# The discrepancy exists specifically because:
# - Pyright: Recognizes @attrs.frozen, synthesizes proper __init__ signature
# - Pyrefly: Falls back to object.__init__ since it doesn't understand attrs
#
# This is a library-specific type checker feature, not reproducible with
# typing-only imports.
