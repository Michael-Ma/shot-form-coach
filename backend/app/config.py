from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    data_dir: Path
    api_key: str = ""
    model_id: str = "gemini-3.8-flash"
    workbench_data: Path | None = None
    max_upload_mb: int = 512

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        source = os.getenv("SFC_WORKBENCH_DATA", "")
        return cls(
            Path((os.getenv("SFC_DATA_DIR") or str(ROOT / ".data"))).resolve(),
            os.getenv("GEMINI_API_KEY", ""),
            (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"),
            Path(source).resolve() if source else None,
        )

    def prepare(self):
        for directory in ["assets", "reports", "models", "receipts"]:
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self):
        return self.data_dir / "state.sqlite3"

    def resolve(self, relative: str):
        path = (self.data_dir / relative).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):
            raise ValueError("Artifact path is outside the data directory")
        return path
