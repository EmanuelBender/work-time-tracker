"""WorktimeTracker — automatic, project-folder-aware time tracking for freelancers."""

from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().with_name("VERSION")
__version__ = _VERSION_FILE.read_text(encoding="utf-8").strip()
if not __version__ or "\n" in __version__ or "\r" in __version__:
    raise RuntimeError(f"Invalid WorktimeTracker product version in {_VERSION_FILE}")
