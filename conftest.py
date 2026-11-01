"""Make the project root importable for tests (scripts, etc.)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
