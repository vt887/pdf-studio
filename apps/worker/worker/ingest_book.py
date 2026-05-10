from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import sys
import shutil
import uuid
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fitz
from document_model import StubPageInput, build_stub_document_model_from_pages, save_document_model
from pdf_renderer import render_document
from worker.spread import SpreadMode, SpreadDetectionResult, classify_spread, crop_boxes_for_spread, load_spread_overrides
from worker.ocr import OcrEngine, OcrError, OcrPageResult, TesseractOcrEngine, apply_ocr_results

TARGET_DPI = 300
SUPPORTED_TYPES = {"png", "jpeg", "tiff", "pdf"}


class IngestError(RuntimeError):
    def __init__(self, message: str, *, stage: str | None = None, path: str | Path | None = None, suggestion: str | None = None) -> None:
        self.message = message
        self.stage = stage
        self.path = str(path) if path is not None else None
        self.suggestion = suggestion
        super().__init__(self._format())

    def _format(self) -> str:
        parts = []
        if self.stage:
            parts.append(f"[{self.stage}]")
        parts.append(self.message)
        if self.path:
            parts.append(f"path={self.path}")
        if self.suggestion:
            parts.append(f"suggestion={self.suggestion}")
        return " ".join(parts)


@dataclass(slots=True)
class OrderedSource:
    path: Path
    file_type: str
    created_at: str
    modified_at: str
    file_size: int
    sha256: str
    order_time: float
    strategy_used: str


@dataclass(slots=True)
class PageBuildResult:
    manifest_entry: dict[str, object]
    page_input: StubPageInput
    preprocess_entry: dict[str, object]
    preprocess_path: Path
    artifacts_rebuilt: bool


@dataclass(slots=True)
class StageRecord:
    name: str
    status: str
    started_at: str
    finished_at: str | None = None
    duration_ms: int | None = None
    key_outputs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunSummary:
    document_id: str | None = None
    input_dir: str = ""
    output_dir: str = ""
    spread_mode: str = "auto-mixed"
    pages_count: int = 0
    manifest_path: str = ""
    model_path: str = ""
    pdf_path: str = ""
    artifacts_dir: str = ""
    warnings: list[str] = field(default_factory=list)
    stages: list[StageRecord] = field(default_factory=list)
    render: dict[str, Any] = field(default_factory=dict)
    spread_detection: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "input_dir": self.input_dir,
            "output_dir": self.output_dir,
            "spread_mode": self.spread_mode,
            "pages_count": self.pages_count,
            "manifest_path": self.manifest_path,
            "model_path": self.model_path,
            "pdf_path": self.pdf_path,
            "artifacts_dir": self.artifacts_dir,
            "warnings": self.warnings,
            "stages": [asdict(stage) for stage in self.stages],
            "render": self.render,
            "spread_detection": self.spread_detection,
        }


@dataclass(slots=True)
class PipelineLogger:
    quiet: bool = False
    verbose: bool = False

    def stage(self, prefix: str, message: str) -> None:
        if not self.quiet:
            print(f"[{prefix}] {message}", flush=True)

    def detail(self, prefix: str, message: str) -> None:
        if self.verbose and not self.quiet:
            print(f"[{prefix}] {message}", flush=True)

    def warn(self, message: str) -> None:
        print(f"[warn] {message}", file=sys.stderr, flush=True)

    def error(self, message: str) -> None:
        print(f"[error] {message}", file=sys.stderr, flush=True)


def deskew_placeholder(image):
    return image


def _detect_input_type(source_path: Path) -> str:
    header = source_path.read_bytes()[:16]
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(header) >= 3 and header[0:3] == b"\xff\xd8\xff":
        return "jpeg"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "tiff"
    if header.startswith(b"%PDF-"):
        return "pdf"
    raise IngestError(
        "Unsupported file type",
        stage="ingest",
        path=source_path,
        suggestion="Use PNG, JPEG, TIFF, or PDF scans.",
    )


def _natural_sort_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _new_stage_record(name: str) -> tuple[StageRecord, float]:
    return StageRecord(name=name, status="running", started_at=_now_iso()), time.perf_counter()


def _finish_stage(record: StageRecord, started: float, *, status: str = "completed", key_outputs: dict[str, Any] | None = None) -> None:
    record.status = status
    record.finished_at = _now_iso()
    record.duration_ms = max(int((time.perf_counter() - started) * 1000), 0)
    record.key_outputs = key_outputs or {}


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _ordered_sources(input_dir: Path) -> tuple[list[OrderedSource], str, bool]:
    if not input_dir.exists():
        raise IngestError(
            "Input directory does not exist",
            stage="ingest",
            path=input_dir,
            suggestion="Create the `book/` directory and place supported scans inside it.",
        )
    if not input_dir.is_dir():
        raise IngestError(
            "Input path is not a directory",
            stage="ingest",
            path=input_dir,
            suggestion="Pass a directory path, not a file.",
        )
    candidates = sorted([p for p in input_dir.iterdir() if p.is_file() and not p.name.startswith(".")], key=lambda p: p.name.lower())
    if not candidates:
        raise IngestError(
            "Input directory is empty",
            stage="ingest",
            path=input_dir,
            suggestion="Add PNG, JPEG, TIFF, or PDF files to the input directory.",
        )

    typed: list[tuple[Path, str]] = []
    for path in candidates:
        if path.name == "spread-overrides.json":
            continue
        file_type = _detect_input_type(path)
        typed.append((path, file_type))

    has_images = any(file_type in {"png", "jpeg", "tiff"} for _, file_type in typed)
    if has_images:
        typed = [(path, file_type) for path, file_type in typed if file_type in {"png", "jpeg", "tiff"}]
    if not typed:
        raise IngestError(
            "No supported files found",
            stage="ingest",
            path=input_dir,
            suggestion="Add PNG, JPEG, TIFF, or PDF scans.",
        )

    rows: list[OrderedSource] = []
    strategies: set[str] = set()
    for path, file_type in typed:
        stat = path.stat()
        birth = getattr(stat, "st_birthtime", None)
        if birth and birth > 0:
            order_time = float(birth)
            strategy_used = "birthtime"
        elif stat.st_mtime:
            order_time = float(stat.st_mtime)
            strategy_used = "mtime"
        else:
            order_time = 0.0
            strategy_used = "natural_filename"
        strategies.add(strategy_used)
        rows.append(
            OrderedSource(
                path=path,
                file_type=file_type,
                created_at=_iso(birth if birth and birth > 0 else stat.st_mtime),
                modified_at=_iso(stat.st_mtime),
                file_size=stat.st_size,
                sha256=_sha256(path),
                order_time=order_time,
                strategy_used=strategy_used,
            )
        )
    rows.sort(key=lambda item: (item.order_time, _natural_sort_key(item.path.name)))
    identical_ts = len({row.order_time for row in rows}) < len(rows)
    ordering_strategy = "birthtime->mtime->natural_filename"
    if "birthtime" not in strategies:
        ordering_strategy = "mtime->natural_filename"
    return rows, ordering_strategy, identical_ts


def _has_exif_rotation(image) -> bool:
    with contextlib.suppress(Exception):
        exif = image.getexif()
        orientation = exif.get(274) if exif else None
        return orientation in {2, 3, 4, 5, 6, 7, 8}
    return False


def _normalize_image(image, *, contrast: bool = False) -> tuple[Any, bool]:
    from PIL import ImageOps

    autorotate_applied = _has_exif_rotation(image)
    image = ImageOps.exif_transpose(image)
    image = deskew_placeholder(image)
    image = image.convert("RGB")
    if contrast:
        image = ImageOps.autocontrast(image)
    return image, autorotate_applied


def _artifact_paths(pages_dir: Path, page_number: int, source_path: Path) -> tuple[Path, Path]:
    suffix = source_path.suffix.lower() or ".bin"
    original_artifact = pages_dir / f"{page_number:04d}.original{suffix}"
    normalized_artifact = pages_dir / f"{page_number:04d}.normalized.png"
    return original_artifact, normalized_artifact


def _preprocess_artifact_path(pages_dir: Path, page_number: int) -> Path:
    return pages_dir / f"{page_number:04d}.preprocess.json"


def _source_artifact_path(sources_dir: Path, source_index: int, source_path: Path) -> Path:
    suffix = source_path.suffix.lower() or ".bin"
    return sources_dir / f"{source_index:04d}.source{suffix}"


def _copy_source_artifact(source_path: Path, source_artifact: Path) -> None:
    source_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, source_artifact)


def _crop_source_image(image, crop_box: tuple[int, int, int, int]):
    return image.crop(crop_box)


def _copy_original_artifact(source_path: Path, original_artifact: Path) -> None:
    original_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, original_artifact)


def _open_raster_source_page(source_path: Path, file_type: str, source_page_index: int):
    from PIL import Image

    if file_type in {"png", "jpeg"}:
        with Image.open(source_path) as image:
            return image.copy()
    if file_type == "tiff":
        with Image.open(source_path) as image:
            frame_index = max(source_page_index - 1, 0)
            if frame_index >= getattr(image, "n_frames", 1):
                raise IngestError(
                    "TIFF frame index out of range",
                    stage="preprocess",
                    path=source_path,
                    suggestion="Check the source TIFF or rebuild the manifest with `--force`.",
                )
            image.seek(frame_index)
            return image.copy()
    if file_type == "pdf":
        with fitz.open(source_path) as pdf:
            page_index = max(source_page_index - 1, 0)
            if page_index >= pdf.page_count:
                raise IngestError(
                    "PDF page index out of range",
                    stage="preprocess",
                    path=source_path,
                    suggestion="Check the manifest page index or rebuild with `--force`.",
                )
            pdf_page = pdf[page_index]
            matrix = fitz.Matrix(TARGET_DPI / 72.0, TARGET_DPI / 72.0)
            pix = pdf_page.get_pixmap(matrix=matrix, alpha=False)
            return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    raise IngestError(
        "Unsupported file type during page rasterization",
        stage="preprocess",
        path=source_path,
        suggestion="Use PNG, JPEG, TIFF, or PDF scans.",
    )


def _materialize_page_artifacts(
    *,
    source_path: Path,
    source_artifact: Path,
    file_type: str,
    source_index: int,
    source_page_count: int,
    source_page_index: int,
    page_number: int,
    pages_dir: Path,
    created_at: str,
    modified_at: str,
    file_size: int,
    sha256: str,
    page_total: int,
    crop_box_px: tuple[int, int, int, int],
    side: str,
    spread_mode: str,
    spread_decision: SpreadDetectionResult,
    force: bool,
    allow_regen_missing: bool,
    logger: PipelineLogger | None = None,
) -> PageBuildResult:
    original_artifact = source_artifact
    normalized_artifact = pages_dir / f"{page_number:04d}.normalized.png"
    preprocess_path = _preprocess_artifact_path(pages_dir, page_number)

    if logger is not None:
        logger.stage(
            "preprocess",
            f"page={page_number:04d} ({page_number} of {page_total}) source={source_path.name} frame={source_page_index} type={file_type}",
        )

    raw_image = _open_raster_source_page(source_path, file_type, source_page_index)
    original_width_px, original_height_px = raw_image.size
    cropped_image = _crop_source_image(raw_image, crop_box_px)
    cropped_width_px, cropped_height_px = cropped_image.size
    need_original = force or not original_artifact.exists()
    need_normalized = force or not normalized_artifact.exists()
    if not allow_regen_missing and (need_original or need_normalized):
        missing = [str(path) for path in (original_artifact, normalized_artifact) if not path.exists()]
        raise IngestError(
            "Manifest references missing page artifacts",
            stage="preprocess",
            path=", ".join(missing) if missing else normalized_artifact,
            suggestion="Run `python -m worker.ingest_book --input book/ --output output/ --force` to rebuild artifacts.",
        )

    normalized_image, autorotate_applied = _normalize_image(cropped_image)
    normalized_width_px, normalized_height_px = normalized_image.size

    if need_original:
        _copy_source_artifact(source_path, original_artifact)
    if need_normalized:
        normalized_image.save(normalized_artifact, format="PNG", dpi=(TARGET_DPI, TARGET_DPI))

    from PIL import Image

    with Image.open(normalized_artifact) as normalized_check:
        if normalized_check.mode != "RGB":
            raise IngestError(
                "Normalized artifact is not RGB PNG",
                stage="preprocess",
                path=normalized_artifact,
                suggestion="Run `python -m worker.ingest_book --input book/ --output output/ --force` to regenerate normalized artifacts.",
            )
        normalized_width_px, normalized_height_px = normalized_check.size

    if not original_artifact.exists():
        raise IngestError(
            "Missing original artifact",
            stage="preprocess",
            path=original_artifact,
            suggestion="Run `python -m worker.ingest_book --input book/ --output output/ --force` to recopy original artifacts.",
        )
    if not normalized_artifact.exists():
        raise IngestError(
            "Missing normalized artifact",
            stage="preprocess",
            path=normalized_artifact,
            suggestion="Run `python -m worker.ingest_book --input book/ --output output/ --force` to regenerate normalized artifacts.",
        )

    width_pt = normalized_width_px * 72.0 / TARGET_DPI
    height_pt = normalized_height_px * 72.0 / TARGET_DPI
    preprocess_payload = {
        "source_index": source_index,
        "page_number": page_number,
        "source_file": str(source_path),
        "source_artifact": str(original_artifact),
        "original_artifact": str(original_artifact),
        "normalized_artifact": str(normalized_artifact),
        "original_width_px": original_width_px,
        "original_height_px": original_height_px,
        "crop_box_px": list(crop_box_px),
        "side": side,
        "spread_mode": spread_mode,
        "detected_type": spread_decision.detected_type,
        "effective_type": spread_decision.effective_type,
        "classification_source": spread_decision.classification_source,
        "detection_confidence": spread_decision.detection_confidence,
        "detection_signals": spread_decision.detection_signals,
        "normalized_width_px": normalized_width_px,
        "normalized_height_px": normalized_height_px,
        "mode": "RGB",
        "dpi": TARGET_DPI,
        "autorotate_applied": autorotate_applied,
        "deskew_applied": False,
        "warnings": ["EXIF autorotation applied"] if autorotate_applied else [],
        "spread_warnings": [],
    }
    _write_json(preprocess_path, preprocess_payload)

    manifest_entry = {
        "source_index": source_index,
        "page_number": page_number,
        "side": side,
        "source_page_index": source_page_index,
        "source_page_count": source_page_count,
        "source_file": str(source_path),
        "source_artifact": str(original_artifact),
        "original_artifact": str(original_artifact),
        "normalized_artifact": str(normalized_artifact),
        "crop_box_px": list(crop_box_px),
        "detected_type": spread_decision.detected_type,
        "effective_type": spread_decision.effective_type,
        "classification_source": spread_decision.classification_source,
        "detection_confidence": spread_decision.detection_confidence,
        "detection_signals": spread_decision.detection_signals,
        "created_at": created_at,
        "modified_at": modified_at,
        "file_size": file_size,
        "sha256": sha256,
        "width_px": cropped_width_px,
        "height_px": cropped_height_px,
        "normalized_width_px": normalized_width_px,
        "normalized_height_px": normalized_height_px,
        "dpi": TARGET_DPI,
    }
    page_input = StubPageInput(
        page_number=page_number,
        width_px=normalized_width_px,
        height_px=normalized_height_px,
        width_pt=width_pt,
        height_pt=height_pt,
        dpi=TARGET_DPI,
        original_image_path=str(original_artifact),
        normalized_image_path=str(normalized_artifact),
    )
    if logger is not None:
        logger.detail("preprocess", json.dumps(preprocess_payload, indent=2))
    return PageBuildResult(
        manifest_entry=manifest_entry,
        page_input=page_input,
        preprocess_entry=preprocess_payload,
        preprocess_path=preprocess_path,
        artifacts_rebuilt=need_original or need_normalized,
    )


def _ocr_artifact_path(ocr_dir: Path, page_number: int) -> Path:
    return ocr_dir / f"{page_number:04d}.ocr.json"


def _load_ocr_artifact(path: Path) -> OcrPageResult:
    return OcrPageResult.model_validate_json(path.read_text(encoding="utf-8"))


def _write_ocr_artifact(path: Path, result: OcrPageResult) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def _materialize_ocr_result(
    *,
    engine: OcrEngine,
    normalized_artifact: Path,
    page_number: int,
    dpi: int,
    language: str,
    ocr_dir: Path,
    force: bool,
    artifacts_rebuilt: bool,
) -> OcrPageResult:
    ocr_path = _ocr_artifact_path(ocr_dir, page_number)
    if not force and not artifacts_rebuilt and ocr_path.exists():
        return _load_ocr_artifact(ocr_path)
    result = engine.recognize_page(normalized_artifact, page_number, dpi, language)
    _write_ocr_artifact(ocr_path, result)
    return result


def _load_manifest(manifest_path: Path) -> dict[str, object] | None:
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _manifest_pages_from_existing(manifest_payload: dict[str, object]) -> list[dict[str, object]]:
    pages = manifest_payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise IngestError(
            "Existing manifest is missing pages",
            stage="manifest",
            suggestion="Rebuild the manifest with `--force`.",
        )
    source_counts: dict[str, int] = {}
    normalized_pages: list[dict[str, object]] = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise IngestError(
                "Existing manifest contains invalid page entries",
                stage="manifest",
                suggestion="Rebuild the manifest with `--force`.",
            )
        source_file = str(page.get("source_file", ""))
        if not source_file:
            raise IngestError(
                "Existing manifest contains a page without source_file",
                stage="manifest",
                suggestion="Rebuild the manifest with `--force`.",
            )
        source_counts[source_file] = source_counts.get(source_file, 0) + 1
        page_copy = dict(page)
        page_copy.setdefault("page_number", index)
        page_copy.setdefault("source_page_index", source_counts[source_file])
        normalized_pages.append(page_copy)
    return normalized_pages


def _process_existing_manifest_pages(
    *,
    manifest_payload: dict[str, object],
    output_dir: Path,
    force: bool,
    logger: PipelineLogger | None = None,
) -> tuple[dict[str, object], list[StubPageInput], dict[int, bool]]:
    pages_dir = output_dir / "artifacts" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    manifest_pages = _manifest_pages_from_existing(manifest_payload)
    total_pages = len(manifest_pages)
    page_inputs: list[StubPageInput] = []
    rebuilt_pages: list[dict[str, object]] = []
    rebuilt_map: dict[int, bool] = {}
    for page in manifest_pages:
        source_path = Path(str(page["source_file"]))
        if not source_path.exists():
            raise IngestError(
                "Manifest references missing source file",
                stage="manifest",
                path=source_path,
                suggestion="Restore the source file or rebuild the manifest with `--force`.",
        )
        file_type = _detect_input_type(source_path)
        page_number = int(page["page_number"])
        source_page_index = int(page.get("source_page_index", 1))
        stat = source_path.stat()
        source_artifact_value = page.get("source_artifact") or page.get("original_artifact")
        if source_artifact_value:
            source_artifact = Path(str(source_artifact_value))
        else:
            source_artifact = _source_artifact_path(output_dir / "artifacts" / "sources", int(page.get("source_index", page_number)), source_path)
        crop_box_value = page.get("crop_box_px")
        if isinstance(crop_box_value, list) and len(crop_box_value) == 4:
            crop_box_px = tuple(int(v) for v in crop_box_value)  # type: ignore[assignment]
        else:
            raw_image = _open_raster_source_page(source_path, file_type, source_page_index)
            crop_box_px = (0, 0, raw_image.size[0], raw_image.size[1])
        side = str(page.get("side", "single"))
        spread_mode = str(manifest_payload.get("spread_mode", "auto-mixed"))
        detected_type = str(page.get("detected_type", "single-page"))
        effective_type = str(page.get("effective_type", "single-page"))
        classification_source = str(page.get("classification_source", "detector"))
        detection_confidence = page.get("detection_confidence")
        detection_signals = page.get("detection_signals", {})
        spread_decision = SpreadDetectionResult(
            detected_type=detected_type,  # type: ignore[arg-type]
            effective_type=effective_type,  # type: ignore[arg-type]
            classification_source=classification_source,  # type: ignore[arg-type]
            detection_confidence=float(detection_confidence) if detection_confidence is not None else None,
            detection_signals={k: float(v) for k, v in detection_signals.items()} if isinstance(detection_signals, dict) else {},
            override_value=page.get("override_value"),
        )
        result = _materialize_page_artifacts(
            source_path=source_path,
            source_artifact=source_artifact,
            file_type=file_type,
            source_index=int(page.get("source_index", page_number)),
            source_page_count=int(page.get("source_page_count", 1)),
            page_number=page_number,
            source_page_index=source_page_index,
            pages_dir=pages_dir,
            created_at=str(page.get("created_at", _iso(stat.st_mtime))),
            modified_at=str(page.get("modified_at", _iso(stat.st_mtime))),
            file_size=int(page.get("file_size", stat.st_size)),
            sha256=str(page.get("sha256", _sha256(source_path))),
            page_total=total_pages,
            crop_box_px=crop_box_px,
            side=side,
            spread_mode=spread_mode,
            spread_decision=spread_decision,
            force=force,
            allow_regen_missing=False,
            logger=logger,
        )
        rebuilt_pages.append(result.manifest_entry)
        page_inputs.append(result.page_input)
        rebuilt_map[result.page_input.page_number] = result.artifacts_rebuilt

    created_at = str(manifest_payload.get("created_at", datetime.now(tz=UTC).isoformat()))
    document_id = str(manifest_payload.get("document_id", uuid.uuid4().hex))
    ordering_strategy = str(manifest_payload.get("ordering_strategy", "manifest_order"))
    warning_identical_timestamps = bool(manifest_payload.get("warning_identical_timestamps", False))
    rebuilt_manifest = {
        "document_id": document_id,
        "source_dir": str(manifest_payload.get("source_dir", "")),
        "output_dir": str(manifest_payload.get("output_dir", output_dir)),
        "ordering_strategy": ordering_strategy,
        "created_at": created_at,
        "warning_identical_timestamps": warning_identical_timestamps,
        "pages": rebuilt_pages,
    }
    return rebuilt_manifest, page_inputs, rebuilt_map


def _build_manifest_from_sources(
    input_dir: Path,
    output_dir: Path,
    *,
    spread_mode: SpreadMode,
    force: bool,
    logger: PipelineLogger | None = None,
) -> tuple[dict[str, object], list[StubPageInput], dict[int, bool]]:
    sources_dir = output_dir / "artifacts" / "sources"
    pages_dir = output_dir / "artifacts" / "pages"
    sources_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)
    ordered, ordering_strategy, identical_ts = _ordered_sources(input_dir)
    overrides: dict[str, str] = {}
    if spread_mode in {"auto", "auto-mixed"}:
        try:
            overrides = load_spread_overrides(input_dir)
        except ValueError as exc:
            raise IngestError(
                str(exc),
                stage="spread-detect",
                path=input_dir / "spread-overrides.json",
                suggestion="Use only `single-page` or `two-page` override values.",
            ) from exc
        missing_overrides = sorted(name for name in overrides if name not in {source.path.name for source in ordered})
        if missing_overrides:
            raise IngestError(
                "spread override references missing file",
                stage="spread-detect",
                path=input_dir / "spread-overrides.json",
                suggestion=f"Remove overrides for: {', '.join(missing_overrides)}",
            )

    document_id = uuid.uuid4().hex
    page_inputs: list[StubPageInput] = []
    sources: list[dict[str, object]] = []
    flat_pages: list[dict[str, object]] = []
    rebuilt_map: dict[int, bool] = {}
    page_number = 0
    source_index = 0
    source_plans: list[dict[str, Any]] = []

    for source in ordered:
        logger.stage("manifest", f"source={source.path.name} type={source.file_type}")
        page_count = 1
        if source.file_type == "tiff":
            from PIL import Image

            with Image.open(source.path) as image:
                page_count = getattr(image, "n_frames", 1)
        elif source.file_type == "pdf":
            with fitz.open(source.path) as pdf:
                page_count = pdf.page_count
        logger.detail("manifest", f"source={source.path.name} pages={page_count}")
        for source_page_index in range(1, page_count + 1):
            source_index += 1
            source_artifact = _source_artifact_path(sources_dir, source_index, source.path)
            if force or not source_artifact.exists():
                _copy_source_artifact(source.path, source_artifact)

            raw_image = _open_raster_source_page(source.path, source.file_type, source_page_index)
            override_value = overrides.get(source.path.name) if spread_mode in {"auto", "auto-mixed"} else None
            decision = classify_spread(raw_image, spread_mode=spread_mode, override_value=override_value)  # type: ignore[arg-type]
            if spread_mode in {"auto", "auto-mixed"} and decision.detected_type == "uncertain" and decision.classification_source != "override":
                raise IngestError(
                    "uncertain source",
                    stage="spread-detect",
                    path=source.path,
                    suggestion="rerun with explicit --spread-mode single-page/two-page or add book/spread-overrides.json",
                )
            if spread_mode == "auto":
                source_plans.append(
                    {
                        "source_index": source_index,
                        "source_path": source.path,
                        "source_page_index": source_page_index,
                        "source_page_count": page_count,
                        "file_type": source.file_type,
                        "source_artifact": source_artifact,
                        "created_at": source.created_at,
                        "modified_at": source.modified_at,
                        "file_size": source.file_size,
                        "sha256": source.sha256,
                        "decision": decision,
                        "raw_image": raw_image,
                    }
                )
                continue

            source_plans.append(
                {
                    "source_index": source_index,
                    "source_path": source.path,
                    "source_page_index": source_page_index,
                    "source_page_count": page_count,
                    "file_type": source.file_type,
                    "source_artifact": source_artifact,
                    "created_at": source.created_at,
                    "modified_at": source.modified_at,
                    "file_size": source.file_size,
                    "sha256": source.sha256,
                    "decision": decision,
                    "raw_image": raw_image,
                }
            )

    if spread_mode == "auto":
        detected_types = {plan["decision"].effective_type for plan in source_plans if plan["decision"].detected_type != "uncertain"}
        if any(plan["decision"].detected_type == "uncertain" for plan in source_plans):
            uncertain_plan = next(plan for plan in source_plans if plan["decision"].detected_type == "uncertain")
            raise IngestError(
                "uncertain source",
                stage="spread-detect",
                path=uncertain_plan["source_path"],
                suggestion="rerun with explicit --spread-mode single-page/two-page or add book/spread-overrides.json",
            )
        if len(detected_types) != 1:
            raise IngestError(
                "mixed spread types detected in auto mode",
                stage="spread-detect",
                path=input_dir,
                suggestion="Use --spread-mode auto-mixed, or force single-page/two-page, or add book/spread-overrides.json.",
            )
        chosen = next(iter(detected_types))
        for plan in source_plans:
            plan["decision"] = SpreadDetectionResult(
                detected_type=plan["decision"].detected_type,
                effective_type=chosen,  # type: ignore[arg-type]
                classification_source=plan["decision"].classification_source,
                detection_confidence=plan["decision"].detection_confidence,
                detection_signals=plan["decision"].detection_signals,
                override_value=plan["decision"].override_value,
            )

    if not source_plans:
        raise IngestError(
            "No extractable pages found",
            stage="manifest",
            path=input_dir,
            suggestion="Add supported scan files to the input directory.",
        )

    detection_counts = {
        "single_page_count": sum(1 for plan in source_plans if plan["decision"].effective_type == "single-page"),
        "two_page_count": sum(1 for plan in source_plans if plan["decision"].effective_type == "two-page"),
        "uncertain_count": sum(1 for plan in source_plans if plan["decision"].detected_type == "uncertain"),
        "overridden_count": sum(1 for plan in source_plans if plan["decision"].classification_source == "override"),
    }
    total_pages = sum(2 if plan["decision"].effective_type == "two-page" else 1 for plan in source_plans)
    for plan in source_plans:
        decision: SpreadDetectionResult = plan["decision"]

        if logger is not None:
            source_label = f"{int(plan['source_index']):04d} {plan['source_path'].name} -> {decision.effective_type}"
            if decision.classification_source == "detector" and decision.detection_confidence is not None:
                logger.stage(
                    "spread-detect",
                    f"{source_label} score={decision.detection_confidence:.2f} source={decision.classification_source}",
                )
            else:
                logger.stage("spread-detect", f"{source_label} source={decision.classification_source}")

        crop_boxes = crop_boxes_for_spread(plan["raw_image"].size, decision.effective_type)
        source_entry_pages: list[dict[str, object]] = []
        for crop_box_px, side in [((box[0], box[1], box[2], box[3]), box[4]) for box in crop_boxes]:
            page_number += 1
            result = _materialize_page_artifacts(
                source_path=plan["source_path"],
                source_artifact=plan["source_artifact"],
                file_type=plan["file_type"],
                source_index=int(plan["source_index"]),
                source_page_count=int(plan["source_page_count"]),
                source_page_index=int(plan["source_page_index"]),
                page_number=page_number,
                pages_dir=pages_dir,
                created_at=str(plan["created_at"]),
                modified_at=str(plan["modified_at"]),
                file_size=int(plan["file_size"]),
                sha256=str(plan["sha256"]),
                page_total=total_pages,
                crop_box_px=crop_box_px,
                side=side,
                spread_mode=str(spread_mode),
                spread_decision=decision,
                force=force,
                allow_regen_missing=True,
                logger=logger,
            )
            source_entry_pages.append({
                "page_number": page_number,
                "side": side,
                "crop_box_px": list(crop_box_px),
                "source_artifact": str(plan["source_artifact"]),
                "normalized_artifact": str(result.manifest_entry["normalized_artifact"]),
            })
            flat_pages.append(result.manifest_entry)
            page_inputs.append(result.page_input)
            rebuilt_map[result.page_input.page_number] = result.artifacts_rebuilt

        sources.append(
            {
                "source_index": int(plan["source_index"]),
                "source_file": str(plan["source_path"]),
                "source_page_index": int(plan["source_page_index"]),
                "source_page_count": int(plan["source_page_count"]),
                "source_artifact": str(plan["source_artifact"]),
                "detected_type": decision.detected_type,
                "effective_type": decision.effective_type,
                "classification_source": decision.classification_source,
                "detection_confidence": decision.detection_confidence,
                "detection_signals": decision.detection_signals,
                "derived_pages": source_entry_pages,
            }
        )

    if not flat_pages:
        raise IngestError(
            "No extractable pages found",
            stage="manifest",
            path=input_dir,
            suggestion="Add supported scan files to the input directory.",
        )

    manifest_payload = {
        "document_id": document_id,
        "source_dir": str(input_dir),
        "output_dir": str(output_dir),
        "ordering_strategy": ordering_strategy,
        "created_at": datetime.now(tz=UTC).isoformat(),
        "warning_identical_timestamps": identical_ts,
        "spread_mode": spread_mode,
        "source_files_count": len(sources),
        "pages_count": total_pages,
        "spread_detection": {
            "strategy": "heuristic_v1" if spread_mode in {"auto", "auto-mixed"} else f"forced_{spread_mode}",
            **detection_counts,
        },
        "sources": sources,
        "pages": flat_pages,
    }
    if logger is not None:
        logger.stage("spread-detect", f"mode: {spread_mode}")
        logger.stage("spread-detect", f"source files: {manifest_payload['source_files_count']}")
        logger.stage("spread-detect", f"single-page: {detection_counts['single_page_count']}")
        logger.stage("spread-detect", f"two-page: {detection_counts['two_page_count']}")
        logger.stage("spread-detect", f"uncertain: {detection_counts['uncertain_count']}")
    return manifest_payload, page_inputs, rebuilt_map


def _write_manifest(output_dir: Path, payload: dict) -> Path:
    path = output_dir / "book.manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_summary(output_dir: Path, payload: RunSummary) -> Path:
    path = output_dir / "book.summary.json"
    _write_json(path, payload.to_dict())
    return path


def _render_counts(document) -> dict[str, int]:
    return {
        "pages_rendered": len(document.pages),
        "image_assets_rendered": sum(len(page.assets) for page in document.pages),
        "text_lines_rendered": sum(len(page.text_lines) for page in document.pages),
        "links_rendered": sum(len(page.links) for page in document.pages),
    }


def ingest_book(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    force: bool = False,
    spread_mode: SpreadMode = "auto-mixed",
    ocr: bool = False,
    ocr_lang: str = "eng",
    ocr_engine: OcrEngine | None = None,
    quiet: bool = False,
    verbose: bool = False,
    logger: PipelineLogger | None = None,
) -> dict[str, str]:
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    logger = logger or PipelineLogger(quiet=quiet, verbose=verbose)
    summary = RunSummary(
        input_dir=str(input_dir),
        output_dir=str(output_dir),
        spread_mode=spread_mode,
        artifacts_dir=str(output_dir / "artifacts"),
    )

    stage_ingest, started_ingest = _new_stage_record("ingest")
    summary.stages.append(stage_ingest)
    logger.stage("ingest", f"input={input_dir} output={output_dir}")
    if not input_dir.exists():
        raise IngestError(
            "Input directory does not exist",
            stage="ingest",
            path=input_dir,
            suggestion="Create the `book/` directory and place supported scan files inside it.",
        )
    if not input_dir.is_dir():
        raise IngestError(
            "Input path is not a directory",
            stage="ingest",
            path=input_dir,
            suggestion="Pass a directory that contains scan files.",
        )
    if not any(path.is_file() and not path.name.startswith(".") for path in input_dir.iterdir()):
        raise IngestError(
            "Input directory is empty",
            stage="ingest",
            path=input_dir,
            suggestion="Add PNG, JPEG, TIFF, or PDF files to the input directory.",
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "artifacts" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    ocr_dir = output_dir / "artifacts" / "ocr"
    if ocr:
        ocr_dir.mkdir(parents=True, exist_ok=True)
    _finish_stage(
        stage_ingest,
        started_ingest,
        key_outputs={
            "input_dir": str(input_dir),
            "output_dir": str(output_dir),
            "artifacts_dir": str(output_dir / "artifacts"),
            "ocr_enabled": ocr,
        },
    )

    manifest_path = output_dir / "book.manifest.json"
    stage_manifest, started_manifest = _new_stage_record("manifest")
    summary.stages.append(stage_manifest)
    existing_manifest = None if force else _load_manifest(manifest_path)
    if existing_manifest:
        logger.stage("manifest", f"reusing {manifest_path}")
        manifest_payload, page_inputs, rebuilt_map = _process_existing_manifest_pages(
            manifest_payload=existing_manifest,
            output_dir=output_dir,
            force=force,
            logger=logger,
        )
        manifest_action = "reused"
    else:
        logger.stage("manifest", f"building {manifest_path}")
        manifest_payload, page_inputs, rebuilt_map = _build_manifest_from_sources(
            input_dir,
            output_dir,
            spread_mode=spread_mode,
            force=force,
            logger=logger,
        )
        manifest_action = "created"

    manifest_path = _write_manifest(output_dir, manifest_payload)
    summary.document_id = str(manifest_payload["document_id"])
    summary.manifest_path = str(manifest_path)
    summary.pages_count = len(manifest_payload["pages"])
    summary.spread_mode = str(manifest_payload.get("spread_mode", spread_mode))
    summary.spread_detection = dict(manifest_payload.get("spread_detection", {}))
    if bool(manifest_payload.get("warning_identical_timestamps", False)):
        warning = "identical timestamps detected; natural filename order used for tie-break."
        summary.warnings.append(warning)
        logger.warn(warning)
    _finish_stage(
        stage_manifest,
        started_manifest,
        key_outputs={
            "manifest_path": str(manifest_path),
            "document_id": summary.document_id,
            "pages_count": summary.pages_count,
            "ordering_strategy": str(manifest_payload["ordering_strategy"]),
            "action": manifest_action,
        },
    )

    stage_preprocess, started_preprocess = _new_stage_record("preprocess")
    summary.stages.append(stage_preprocess)
    logger.stage("preprocess", f"materializing {summary.pages_count} page artifacts")
    logger.stage("ingest", f"derived pages: {summary.pages_count}")
    ordered_page_numbers = [int(page["page_number"]) for page in manifest_payload["pages"]]
    input_by_number = {page.page_number: page for page in page_inputs}
    ordered_page_inputs = [input_by_number[number] for number in ordered_page_numbers]
    preprocess_paths: list[str] = []
    for page in manifest_payload["pages"]:
        preprocess_paths.append(str(output_dir / "artifacts" / "pages" / f"{int(page['page_number']):04d}.preprocess.json"))
    _finish_stage(
        stage_preprocess,
        started_preprocess,
        key_outputs={
            "pages_dir": str(pages_dir),
            "preprocess_artifacts": preprocess_paths,
        },
    )

    stage_model, started_model = _new_stage_record("model")
    summary.stages.append(stage_model)
    logger.stage("model", f"building model for {summary.pages_count} pages")
    document = build_stub_document_model_from_pages(
        source_path=input_dir,
        pages=ordered_page_inputs,
        output_pdf_path=output_dir / "book.pdf",
        document_id=str(manifest_payload["document_id"]),
    )
    if ocr:
        try:
            engine = ocr_engine or TesseractOcrEngine()
        except OcrError as exc:
            raise IngestError(str(exc), stage="ocr") from exc
        ocr_results: list[OcrPageResult] = []
        for page in document.pages:
            page_manifest = next(item for item in manifest_payload["pages"] if int(item["page_number"]) == page.page_number)
            normalized_artifact = Path(str(page_manifest["normalized_artifact"]))
            ocr_result = _materialize_ocr_result(
                engine=engine,
                normalized_artifact=normalized_artifact,
                page_number=page.page_number,
                dpi=page.dpi,
                language=ocr_lang,
                ocr_dir=ocr_dir,
                force=force,
                artifacts_rebuilt=rebuilt_map.get(page.page_number, False),
            )
            page_label = f"{page.page_number:04d}"
            word_count = sum(len(line.words) for line in ocr_result.lines)
            confidences = [line.confidence for line in ocr_result.lines if line.confidence is not None]
            avg_conf = f"{sum(confidences) / len(confidences):.2f}" if confidences else "n/a"
            logger.stage("ocr", f"page {page_label} lines: {len(ocr_result.lines)} words: {word_count} avg_confidence: {avg_conf}")
            logger.detail("ocr", f"engine: {ocr_result.engine} language: {ocr_result.language}")
            logger.detail("ocr", f"artifact: {_ocr_artifact_path(ocr_dir, page.page_number)}")
            if not ocr_result.lines:
                logger.stage("ocr:warn", f"page {page_label} produced no text")
            ocr_results.append(ocr_result)
        apply_ocr_results(document, ocr_results)
    model_path = output_dir / "book.model.json"
    save_document_model(document, model_path)
    summary.model_path = str(model_path)
    _finish_stage(
        stage_model,
        started_model,
        key_outputs={
            "model_path": str(model_path),
            "pages": len(document.pages),
            "text_lines": sum(len(page.text_lines) for page in document.pages),
            "image_assets": sum(len(page.assets) for page in document.pages),
        },
    )

    stage_render, started_render = _new_stage_record("render")
    summary.stages.append(stage_render)
    logger.stage("render", f"writing PDF to {output_dir / 'book.pdf'}")
    pdf_path = render_document(document, output_dir / "book.pdf")
    render_counts = _render_counts(document)
    pdf_size = Path(pdf_path).stat().st_size
    summary.pdf_path = str(pdf_path)
    summary.render = {**render_counts, "pdf_file_size": pdf_size}
    logger.stage(
        "render",
        "output={output} pages={pages} image_assets={assets} text_lines={lines} links={links} size={size}".format(
            output=pdf_path,
            pages=render_counts["pages_rendered"],
            assets=render_counts["image_assets_rendered"],
            lines=render_counts["text_lines_rendered"],
            links=render_counts["links_rendered"],
            size=pdf_size,
        ),
    )
    _finish_stage(stage_render, started_render, key_outputs={**render_counts, "pdf_path": str(pdf_path), "pdf_file_size": pdf_size})

    stage_summary, started_summary = _new_stage_record("summary")
    summary.stages.append(stage_summary)
    _finish_stage(
        stage_summary,
        started_summary,
        key_outputs={
            "summary_path": str(output_dir / "book.summary.json"),
            "warnings": summary.warnings,
        },
    )
    summary_path = _write_summary(output_dir, summary)
    logger.stage("summary", f"wrote {summary_path}")

    return {
        "document_id": str(manifest_payload["document_id"]),
        "manifest_path": str(manifest_path),
        "model_path": str(model_path),
        "pdf_path": str(pdf_path),
        "summary_path": str(summary_path),
        "pages_count": str(summary.pages_count),
        "ordering_strategy": str(manifest_payload["ordering_strategy"]),
        "warning_identical_timestamps": str(bool(manifest_payload.get("warning_identical_timestamps", False))).lower(),
        "ocr": str(bool(ocr)).lower(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest book directory into stub model and PDF")
    parser.add_argument("--input", required=True, help="Input book directory path")
    parser.add_argument("--output", required=True, help="Output directory path")
    parser.add_argument("--force", action="store_true", help="Rebuild manifest and regenerate artifacts")
    parser.add_argument(
        "--spread-mode",
        default="auto-mixed",
        choices=["single-page", "two-page", "auto", "auto-mixed"],
        help="Spread detection mode for mixed screenshot books",
    )
    parser.add_argument("--ocr", action="store_true", help="Run OCR on normalized page images")
    parser.add_argument("--ocr-lang", default="eng", help="OCR language code")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--quiet", action="store_true", help="Suppress stage progress logs")
    mode.add_argument("--verbose", action="store_true", help="Print detailed per-page metadata")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        result = ingest_book(
            args.input,
            args.output,
            force=args.force,
            spread_mode=args.spread_mode,
            ocr=args.ocr,
            ocr_lang=args.ocr_lang,
            quiet=args.quiet,
            verbose=args.verbose,
            logger=PipelineLogger(quiet=args.quiet, verbose=args.verbose),
        )
    except IngestError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2), flush=True)


if __name__ == "__main__":
    main()
