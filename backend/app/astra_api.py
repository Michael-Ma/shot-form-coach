"""Astra vision review via the OpenAI Responses API; one HTTP attempt."""

from __future__ import annotations

import base64

import httpx


def call_astra_api(settings, frames, config, schema, instruction):
    content = []
    for frame in frames:
        encoded = base64.b64encode(settings.resolve(frame["path"]).read_bytes()).decode()
        content += [
            {
                "type": "input_text",
                "text": f"FRAME {frame['frame_id']} clip_us={frame['time_us']} view={frame.get('view', 'full_scene')}",
            },
            {"type": "input_image", "image_url": "data:image/jpeg;base64," + encoded, "detail": "high"},
        ]
    body = {
        "model": settings.astra_model,
        "instructions": instruction,
        "input": [{"role": "user", "content": content}],
        "reasoning": {"effort": "low"},
        "max_output_tokens": 16000,
        "store": False,
        "text": {
            "format": {"type": "json_schema", "name": "shot_observation", "schema": schema, "strict": True}
        },
    }
    with httpx.Client(
        timeout=config["request_timeout_s"], transport=httpx.HTTPTransport(retries=0)
    ) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            json=body,
            headers={"Authorization": "Bearer " + settings.openai_api_key},
        )
        response.raise_for_status()
        raw = response.json()
    text = "".join(
        part.get("text", "")
        for item in raw.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    return {
        "text": text,
        "usage": raw.get("usage") or {},
        "model_version": raw.get("model"),
        "response_id": raw.get("id"),
        "response_status": raw.get("status"),
    }
