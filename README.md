# pdf-studio

pdf-studio is a local-first tool for turning scanned book pages and screenshots into clean, searchable, human-reviewable PDF documents.

It takes page scans from `book/`, understands page order, can handle single-page and two-page screenshots, creates normalized page artifacts, builds a structured document model, renders a PDF into `output/`, and keeps a human-readable Obsidian project vault.

## Why pdf-studio?

Many scanning and OCR tools stop at flat page images, lose layout structure, or make it hard to review what happened during processing. Others do not preserve a clear artifact trail, which makes debugging page order, OCR quality, or rendering problems difficult.

pdf-studio is designed around a different approach:

- local-first, so the pipeline runs on your machine
- transparent, so every stage writes explicit artifacts
- reviewable, so processed documents can be inspected and corrected
- deterministic, so page order and outputs are reproducible
- artifact-driven, so the pipeline can be debugged from files, not guesses

The goal is to reconstruct books and documents from scans in a way that remains understandable to humans.

## What it can do today

- Local `book/ -> output/` ingestion.
- Deterministic page ordering by file creation/birth time, with fallback logic.
- Manifest generation that records source files and page order.
- Normalized page image artifacts under `output/artifacts/`.
- Spread modes for screenshots: `single-page`, `two-page`, `auto`, and `auto-mixed`.
- Mixed screenshot ingestion with per-file spread classification and optional overrides.
- Structured document model generation in `output/book.model.json`.
- PDF rendering in `output/book.pdf`.
- Per-run summary output in `output/book.summary.json`.
- Per-page preprocessing metadata under `output/artifacts/pages/`.
- Stage visibility and progress logging during ingestion.
- FastAPI API, Python worker, React review UI, Postgres metadata, and Redis/RQ job queue.
- Poetry-based local development and testing.
- Obsidian vault memory in `pdf-vault/`.
- First OCR extraction stage on normalized page images, with OCR artifacts and searchable PDF text.

## Example: turn scans into a PDF

```bash
mkdir -p book output
# put scans into book/
make ingest-book-auto-mixed-force
open output/book.pdf
```

Expected output files:

```text
output/
  book.manifest.json
  book.model.json
  book.pdf
  book.summary.json
  artifacts/
    pages/
```

## Input model

One `book/` directory corresponds to one book or document.

- The files in `book/` are processed in page order.
- The oldest file comes first.
- The newest file comes last.
- Screenshots may contain one or two pages depending on spread mode.

Supported spread modes:

```text
single-page   one file = one page
two-page      one file = two pages, left then right
auto          detect one mode for the whole batch
auto-mixed    classify each file independently
```

If the input uses mixed screenshot types, `auto-mixed` is usually the right choice.

If needed, `book/spread-overrides.json` can force a file to be treated as `single-page` or `two-page`.

## Output model

The pipeline writes explicit artifacts to `output/`:

- `output/book.manifest.json` records source files, spread classification, and page order.
- `output/book.model.json` is the structured reconstruction model.
- `output/book.pdf` is the rendered PDF.
- `output/book.summary.json` records run-level stage status and render counts.
- `output/artifacts/` contains normalized images and debug/processing artifacts.

## How it works

```text
book/ scans
  -> manifest
  -> normalized page artifacts
  -> document reconstruction model
  -> rendered PDF
  -> output/
```

The runtime stack includes:

- FastAPI API
- Python worker
- React review UI
- Postgres metadata
- Redis/RQ job queue
- filesystem artifacts
- Obsidian vault for project memory

For architecture details, read [docs/SPEC-1-Scan-to-Structured-PDF.md](docs/SPEC-1-Scan-to-Structured-PDF.md).

## Project memory

`pdf-vault/` is the human-readable project memory for this repository.

- Prompts are archived in `pdf-vault/03-prompts/`.
- Implementation reports are archived in `pdf-vault/04-implementation-reports/`.
- Architecture decisions are stored as ADRs in `pdf-vault/05-decisions/`.
- The vault index lives in [pdf-vault/00-index.md](pdf-vault/00-index.md).

This keeps implementation history and design decisions readable after the chat thread is gone.

## Local development

Poetry is the preferred way to create a reproducible local environment.

```bash
make install
make test
make ingest-book-auto-mixed-force
```

Docker Compose is still available for the service-based runtime:

```bash
make up
make migrate
```

This compose stack starts the API, worker, review UI, and a local Postgres service.
Redis is expected to be available on `10.0.1.2` for local service-based runs.
If your host uses different Redis settings, export `REDIS_URL` and `REDIS_KEY_PREFIX` before running `make up`, `make migrate`, or `make full-stack-smoke`.

Useful commands:

```bash
make ingest-book-verbose
make ingest-book-force-verbose
make ingest-book-auto-mixed-force
make inspect-output
```

You can override the local book/output paths:

```bash
BOOK_INPUT=book BOOK_OUTPUT=output make ingest-book-auto-mixed-force
```

## Where OCR runs

OCR executes in the same environment as the ingestion command.

**Local Poetry / Make targets** (`make ingest-book-ocr-force`, etc.) run OCR on the host machine and require Tesseract installed on the host:

```bash
brew install tesseract
# optional: extra language packs
brew install tesseract-lang
```

Example with a non-English language pack:

```bash
OCR_LANG=ukr+eng make ingest-book-ocr-force
```

**Docker worker** runs OCR inside the worker container. The `apps/worker/Dockerfile` now installs `tesseract-ocr` so OCR works out of the box after a rebuild:

```bash
docker compose build worker
```

> Docker-based local ingestion (mounting `book/` and `output/` into the worker container) is not yet wired via `docker compose`. Use the Poetry-based Make targets for local book ingestion. OCR via Docker is used when jobs are submitted through the API.

## OCR smoke test

Verify the full OCR pipeline end-to-end: normalized page image → OCR JSON → Document Reconstruction Model → searchable PDF.

```bash
make smoke-ocr
```

With verbose OCR output:

```bash
make smoke-ocr-verbose
```

With a non-English language pack:

```bash
OCR_LANG=ukr+eng make smoke-ocr
```

The script auto-generates a test image if `book/` is empty, then verifies:

```text
output/book.manifest.json
output/book.model.json
output/book.pdf
output/artifacts/ocr/0001.ocr.json
```

Inspect results manually:

```bash
cat output/artifacts/ocr/0001.ocr.json   # OCR lines and words
cat output/book.model.json               # document model with text_lines
make inspect-output                      # full pipeline summary
```

## Testing

Recommended local checks:

```bash
make test
make test-unit
make test-worker
make test-api
make test-e2e SAMPLE=sample.png
```

For ingestion smoke checks:

```bash
make ingest-book-auto-mixed-force
make inspect-output
```

Some OCR-related checks may require Tesseract to be installed locally. The repo’s Poetry environment is designed to keep the core tests reproducible without depending on ad-hoc global Python packages.

## Full-stack local test

Run the full local stack verification:

```bash
make full-stack-smoke
```

You can override the spread mode and input/output paths:

```bash
SPREAD_MODE=auto-mixed make full-stack-smoke
BOOK_INPUT=book BOOK_OUTPUT=output make full-stack-smoke
```

This smoke workflow builds and starts the Docker Compose stack, runs migrations, checks API and UI health, verifies local Postgres and host Redis, runs local ingestion, and then runs the current unit test slices.

The smoke workflow assumes Redis is already available on `10.0.1.2`.
Use `REDIS_KEY_PREFIX=pdf-studio` to isolate this project’s keys in Redis.
If the host database uses different credentials, set `DATABASE_URL` and `REDIS_URL` explicitly before running the smoke.

Inspect the generated outputs here:

```text
output/book.pdf
output/book.manifest.json
output/book.model.json
output/book.summary.json
```

## Roadmap

Planned capabilities include:

- Layout detection and richer block reconstruction.
- Image region extraction refinements.
- Better font matching beyond best-effort heuristics.
- Clickable URL, email, TOC, and internal link reconstruction.
- Human review editing for OCR, layout, and links.
- QA visual diff workflows for comparing reconstructed PDFs to scans.

## Current limitations

- This is not yet a fully automatic layout reconstruction system.
- Exact font recovery is best-effort when the original font file is not available.
- Automatic spread detection may need overrides for ambiguous screenshots.
- Output quality depends heavily on input scan quality.
- OCR/layout/link reconstruction is still evolving and should be reviewed on real documents.
