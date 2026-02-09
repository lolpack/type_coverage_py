# Repro for pyrefly error on dataclasses-like generated __init__
# This tests if pyrefly handles dataclass-style decorators differently than pyright
from dataclasses import dataclass

@dataclass
class AFDGroup:
    size: int
    handle: int

# This should be valid - dataclass generates __init__(self, size, handle)
afd_group = AFDGroup(0, 123)
