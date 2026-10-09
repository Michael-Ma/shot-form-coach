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
    max_upload_mb: int = 512
    openai_api_key: str = ""
    astra_model: str = "gpt-6-astra"
    codex_bin: str | None = None
    codex_debug: bool = False
    max_video_upload_mb: int = 2048
    max_video_duration_us: int = 60 * 60 * 1_000_000

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env")
        return cls(
            Path((os.getenv("SFC_DATA_DIR") or str(ROOT / ".data"))).resolve(),
            os.getenv("GEMINI_API_KEY", ""),
            (os.getenv("GEMINI_MODEL") or "gemini-3.8-flash"),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            astra_model=os.getenv("ASTRA_MODEL") or "gpt-6-astra",
            codex_bin=os.getenv("SFC_CODEX_BIN") or None,
            codex_debug=os.getenv("SFC_CODEX_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"),
        )

    def prepare(self):
        for directory in ["assets", "videos", "reports", "models", "receipts"]:
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)

    @property
    def db_path(self):
        return self.data_dir / "state.sqlite3"

    def resolve(self, relative: str):
        path = (self.data_dir / relative).resolve()
        if not path.is_relative_to(self.data_dir.resolve()):
            raise ValueError("Artifact path is outside the data directory")
        return path
