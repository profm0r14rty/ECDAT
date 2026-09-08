"""Conftest for backend tests."""
import sys
from pathlib import Path

# Ensure the backend package is importable regardless of CWD
_backend_path = str(Path(__file__).parent.parent / "backend")
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)