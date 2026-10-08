from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "gemini", "astra_api", "astra_codex"] = "local"
    handedness: Literal["auto", "left", "right"] = "auto"
    shot_type: Literal["stationary_jump_shot", "set_shot", "unknown"] = "stationary_jump_shot"
    camera_view: Literal["oblique", "side", "front", "unknown"] = "oblique"
    request_timeout_s: int = Field(default=1200, ge=30, le=3600)
    max_model_calls: int = Field(default=6, ge=1, le=30)
    max_input_frames: int = Field(default=80, ge=8, le=160)
    locale: Literal["en", "zh"] = "en"


class CreateAnalysis(BaseModel):
    asset_ids: list[str] = Field(min_length=1, max_length=30)
    config: AnalysisConfig = Field(default_factory=AnalysisConfig)


class PhaseCorrection(BaseModel):
    locale: Literal["en", "zh"] | None = None
    expected_revision: int = Field(ge=0)
    last_contact_frame: int = Field(ge=0)
    first_clear_frame: int = Field(ge=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.last_contact_frame > self.first_clear_frame:
            raise ValueError("The last-contact frame must be before the first-clear frame")
        return self


class ReportRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    reference_asset_id: str | None = None
    locale: Literal["en", "zh"] = "en"
    assume_same_view: bool = False


class ImportWorkbench(BaseModel):
    run_id: str = Field(pattern=r"^run_[a-zA-Z0-9_]+$")
