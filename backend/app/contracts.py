from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "gemini", "astra_api", "astra_codex"] = "local"
    allow_unknown_retry: bool = False
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


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expected_lifecycle_revision: int = Field(default=0, ge=0)


class AssetLabel(RevisionRequest):
    label: str = Field(min_length=1, max_length=120)


class ClipSpan(BaseModel):
    """Microseconds on the ORIGINAL video's timeline, never relative to a clip."""

    model_config = ConfigDict(extra="forbid")
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    label: str | None = Field(default=None, min_length=1, max_length=120)
    candidate_id: str | None = None

    @model_validator(mode="after")
    def ordered(self):
        if not 0 < self.end_us - self.start_us <= 30_000_000:
            raise ValueError("A clip must be greater than zero and at most 30 seconds")
        return self


class TrimSpan(ClipSpan):
    expected_revision: int = Field(ge=0)
    expected_lifecycle_revision: int = Field(default=0, ge=0)
