import os
import tempfile
from pathlib import Path

_cache = Path(tempfile.gettempdir()) / "shot-form-coach-cache"
(_cache / "matplotlib").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_cache / "matplotlib"))
os.environ.setdefault("XDG_CACHE_HOME", str(_cache))
