"""Tests package for JARVIS."""

import os
import sys

_src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

for _d in (_src_dir, _root_dir):
    if _d not in sys.path:
        sys.path.insert(0, _d)
