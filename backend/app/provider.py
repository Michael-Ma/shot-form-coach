from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .billing import estimate_call_cost, pricing_snapshot
from .db import ident, now


class ModelObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attribute: Literal["follow_through", "rhythm", "visibility"]
    evidence_frame_ids: list[str]
    interpretation: Literal["visible_change", "repeatable", "uncertain"]


class ModelReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_contact_frame_id: str | None
    first_clear_frame_id: str | None
    observations: list[ModelObservation]


def sampled_frames(asset, maximum):
    frames = asset["frame_index"]
    if len(frames) <= maximum:
        return frames
    indices = {round(i * (len(frames) - 1) / (maximum - 1)) for i in range(maximum)}
    # Retain the local release neighbourhood inside the same cap.
    phase = asset.get("phases", {}).get("release")
    priority = (
        set(range(max(0, phase["frame_range"][0] - 2), min(len(frames), phase["frame_range"][1] + 3)))
        if phase
        else set()
    )
    for index in sorted(priority):
        if index not in indices:
            removable = [i for i in indices if i not in priority and i not in (0, len(frames) - 1)]
            if not removable:
                break
            indices.remove(min(removable, key=lambda i: abs(i - index)))
            indices.add(index)
    return [frames[i] for i in sorted(indices)]


def call_sdk(settings, frames, config):
    from google import genai
    from google.genai import types

    parts = []
    for frame in frames:
        parts += [
            types.Part.from_text(text=f"FRAME {frame['frame_id']} clip_us={frame['time_us']}"),
            types.Part.from_bytes(data=settings.resolve(frame["path"]).read_bytes(), mime_type="image/jpeg"),
        ]
    parts.append(
        types.Part.from_text(text="Review this one stationary shooting attempt in chronological order.")
    )
    with genai.Client(
        api_key=settings.api_key,
        http_options=types.HttpOptions(
            timeout=config["request_timeout_s"] * 1000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    ) as client:
        response = client.models.generate_content(
            model=settings.model_id,
            contents=parts,
            config=types.GenerateContentConfig(
                system_instruction="Use only supplied FRAME identifiers. Describe visible projection only. "
                "Find the last visible ball-hand contact and first definite separation, or use null for both. "
                "Do not invent biomechanical numbers or infer why a shot missed. "
                "Observations must cite input frames. Limit observations to three.",
                response_mime_type="application/json",
                response_schema=ModelReply,
                max_output_tokens=16000,
                temperature=1,
                thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            ),
        )
        usage = (
            response.usage_metadata.model_dump(mode="json", exclude_none=True)
            if response.usage_metadata
            else {}
        )
        try:
            returned_text = response.text or ""
        except (ValueError, TypeError):
            returned_text = ""
        return {
            "text": returned_text,
            "usage": usage,
            "model_version": response.model_version,
            "response_id": response.response_id,
        }


def assist(settings, repo, job_id, asset, config, cancelled, transport=None):
    if not settings.api_key:
        raise ValueError("api_key_missing")
    job = repo.get("job", job_id)
    if len(job["receipts"]) >= config["max_model_calls"]:
        raise ValueError("model_call_budget_exhausted")
    for previous in repo.all("job"):
        if any(
            r.get("asset_id") == asset["id"] and r["status"] in ("submitting", "request_unknown")
            for r in previous.get("receipts", [])
        ):
            raise ValueError("unresolved_request_blocks_resubmission")
    frames = sampled_frames(asset, config["max_input_frames"])
    if cancelled():
        raise InterruptedError("cancelled")
    receipt = {
        "id": ident("call"),
        "asset_id": asset["id"],
        "asset_revision": asset["revision"],
        "status": "submitting",
        "submitted_at": now(),
        "model": settings.model_id,
        "input_frame_ids": [f["frame_id"] for f in frames],
        "transport": "ordered_jpeg_frames",
        "timeout_s": config["request_timeout_s"],
        "max_output_tokens": 16000,
        "retry_attempts": 1,
        "cost": {"status": "pending", "estimated_usd": None},
    }
    receipts = job["receipts"] + [receipt]
    repo.patch("job", job_id, receipts=receipts, stage="model_assist")
    snapshot = pricing_snapshot("gemini", settings.model_id, date.today())
    try:
        response = (transport or call_sdk)(settings, frames, config)
    except Exception as exc:
        receipt.update(
            status="request_unknown",
            exception_type=type(exc).__name__,
            cost=estimate_call_cost(snapshot, {}, outcome_unknown=True),
        )
        repo.patch("job", job_id, receipts=receipts)
        raise ValueError("request_unknown") from None
    # Persist usage and the response before validation and late cancellation.
    receipt.update(status="received", response=response, cost=estimate_call_cost(snapshot, response["usage"]))
    repo.patch("job", job_id, receipts=receipts)
    if cancelled():
        receipt["status"] = "received_after_cancel"
        repo.patch("job", job_id, receipts=receipts)
        raise InterruptedError("cancelled")
    try:
        reply = ModelReply.model_validate_json(response["text"])
        by_id = {f["frame_id"]: f for f in frames}
        pair = [reply.last_contact_frame_id, reply.first_clear_frame_id]
        if any(pair) and (not all(pair) or any(p not in by_id for p in pair)):
            raise ValueError("invalid phase evidence")
        if len(reply.observations) > 3 or any(
            not o.evidence_frame_ids or any(f not in by_id for f in o.evidence_frame_ids)
            for o in reply.observations
        ):
            raise ValueError("invalid observation evidence")
        phase = None
        if all(pair):
            a, b = by_id[pair[0]], by_id[pair[1]]
            if a["frame_index"] >= b["frame_index"]:
                raise ValueError("invalid phase order")
            phase = {
                "range_us": [a["time_us"], b["time_us"]],
                "frame_range": [a["frame_index"], b["frame_index"]],
                "source": "gemini_visual_candidate",
                "quality": "needs_review",
                "receipt_id": receipt["id"],
            }
    except (ValueError, TypeError):
        receipt["status"] = "validation_failed"
        repo.patch("job", job_id, receipts=receipts)
        raise ValueError("model_reply_invalid") from None
    receipt["status"] = "validated"
    repo.patch("job", job_id, receipts=receipts)
    return {
        "release": phase,
        "observations": [o.model_dump() for o in reply.observations],
        "receipt_id": receipt["id"],
    }
