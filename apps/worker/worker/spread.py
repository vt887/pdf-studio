from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

SpreadMode = Literal["single-page", "two-page", "auto", "auto-mixed"]
SpreadType = Literal["single-page", "two-page", "uncertain"]
SpreadSide = Literal["single", "left", "right"]


@dataclass(slots=True)
class SpreadDetectionResult:
    detected_type: SpreadType
    effective_type: Literal["single-page", "two-page"]
    classification_source: Literal["detector", "override", "forced"]
    detection_confidence: float | None
    detection_signals: dict[str, float]
    override_value: SpreadType | None = None


def load_spread_overrides(input_dir: Path) -> dict[str, SpreadType]:
    overrides_path = input_dir / "spread-overrides.json"
    if not overrides_path.exists():
        return {}
    payload = json.loads(overrides_path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("spread-overrides.json must contain a top-level `files` object")
    overrides: dict[str, SpreadType] = {}
    for name, value in files.items():
        if value not in {"single-page", "two-page"}:
            raise ValueError(f"Invalid spread override for {name}: {value}")
        overrides[str(name)] = value
    return overrides


def _center_band_white_ratio(image: Image.Image) -> float:
    grayscale = image.convert("L")
    width, height = grayscale.size
    band_width = max(int(width * 0.08), 32)
    left = max((width - band_width) // 2, 0)
    right = min(left + band_width, width)
    band = grayscale.crop((left, 0, right, height))
    pixels = list(band.getdata())
    if not pixels:
        return 0.0
    white = sum(1 for value in pixels if value >= 245)
    return white / len(pixels)


def _center_band_dark_ratio(image: Image.Image) -> float:
    grayscale = image.convert("L")
    width, height = grayscale.size
    band_width = max(int(width * 0.08), 32)
    left = max((width - band_width) // 2, 0)
    right = min(left + band_width, width)
    band = grayscale.crop((left, 0, right, height))
    pixels = list(band.getdata())
    if not pixels:
        return 0.0
    dark = sum(1 for value in pixels if value <= 20)
    return dark / len(pixels)


def detect_spread_type(image: Image.Image) -> tuple[SpreadType, float | None, dict[str, float]]:
    width, height = image.size
    aspect_ratio = round(width / height, 4) if height else 0.0
    center_white_ratio = round(_center_band_white_ratio(image), 4)
    center_dark_ratio = round(_center_band_dark_ratio(image), 4)
    spread_score = round(max(0.0, aspect_ratio - 1.35) + max(0.0, 0.75 - center_white_ratio), 4)
    signals = {
        "aspect_ratio": aspect_ratio,
        "spread_score": spread_score,
        "center_white_ratio": center_white_ratio,
        "center_dark_ratio": center_dark_ratio,
    }

    if aspect_ratio <= 1.2:
        confidence = round(min(0.99, max(0.5, 1.0 - (1.2 - aspect_ratio))), 4)
        return "single-page", confidence, signals
    if aspect_ratio >= 1.55 and (center_white_ratio >= 0.42 or center_dark_ratio >= 0.42):
        confidence = round(min(0.99, max(0.5, min((aspect_ratio - 1.65) / 0.6 + 0.5, 0.99))), 4)
        return "two-page", confidence, signals
    if aspect_ratio >= 1.75:
        return "two-page", 0.5, signals
    return "uncertain", None, signals


def classify_spread(
    image: Image.Image,
    *,
    spread_mode: SpreadMode,
    override_value: SpreadType | None = None,
) -> SpreadDetectionResult:
    detected_type, confidence, signals = detect_spread_type(image)
    if spread_mode == "single-page":
        return SpreadDetectionResult(
            detected_type="single-page",
            effective_type="single-page",
            classification_source="forced",
            detection_confidence=1.0,
            detection_signals=signals,
        )
    if spread_mode == "two-page":
        return SpreadDetectionResult(
            detected_type="two-page",
            effective_type="two-page",
            classification_source="forced",
            detection_confidence=1.0,
            detection_signals=signals,
        )
    if override_value in {"single-page", "two-page"}:
        return SpreadDetectionResult(
            detected_type=detected_type,
            effective_type=override_value,
            classification_source="override",
            detection_confidence=confidence,
            detection_signals=signals,
            override_value=override_value,
        )
    return SpreadDetectionResult(
        detected_type=detected_type,
        effective_type=detected_type if detected_type != "uncertain" else "single-page",
        classification_source="detector",
        detection_confidence=confidence,
        detection_signals=signals,
    )


def crop_boxes_for_spread(image_size: tuple[int, int], effective_type: Literal["single-page", "two-page"]) -> list[tuple[int, int, int, int, SpreadSide]]:
    width, height = image_size
    if effective_type == "single-page":
        return [(0, 0, width, height, "single")]
    midpoint = max(width // 2, 1)
    return [
        (0, 0, midpoint, height, "left"),
        (midpoint, 0, width, height, "right"),
    ]
