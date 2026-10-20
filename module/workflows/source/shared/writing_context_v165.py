"""Run-local compatibility entry for writing_context_fdnv6."""
from .writing_context_fdnv6 import *
from . import writing_context_fdnv6 as _implementation

def __getattr__(name):
    return getattr(_implementation, name)
