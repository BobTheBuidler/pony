import sys, platform
from typing import Final

PYPY: Final = platform.python_implementation() == 'PyPy'
PY36: Final = sys.version_info[:2] >= (3, 6)
PY37: Final = sys.version_info[:2] >= (3, 7)
PY38: Final = sys.version_info[:2] >= (3, 8)
PY39: Final = sys.version_info[:2] >= (3, 9)
PY310: Final = sys.version_info[:2] >= (3, 10)
PY311: Final = sys.version_info[:2] >= (3, 11)
PY312: Final = sys.version_info[:2] >= (3, 12)

unicode = str
buffer = bytes
int_types = (int,)

def cmp(a, b): # type: ignore [no-untyped-def]
    return (a > b) - (a < b)
