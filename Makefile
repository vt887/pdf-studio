SAMPLE ?= sample.png
BOOK_INPUT ?= book
BOOK_OUTPUT ?= output
OCR_LANG ?= eng
PYTHONPATH ?= apps/worker:packages/document-model/src:packages/pdf-renderer/src
POETRY ?= poetry

.PHONY: install up migrate test test-unit test-e2e lint format check stub-render smoke-book smoke-ocr smoke-ocr-verbose ingest-book ingest-book-force ingest-book-verbose ingest-book-force-verbose ingest-book-auto-mixed ingest-book-auto-mixed-force ingest-book-auto-mixed-verbose ingest-book-ocr ingest-book-ocr-force ingest-book-ocr-images-force inspect-output full-stack-smoke gemini-review gemini-review-ocr-plan claude-review claude-review-ocr-plan opencode-review opencode-review-ocr-plan ollama-draft reviewer-healthcheck

install:
	$(POETRY) install

up:
	docker compose up -d --build

migrate:
	docker compose run --rm api alembic -c /app/apps/api/alembic.ini upgrade head

test:
	$(POETRY) run pytest packages/document-model/tests packages/pdf-renderer/tests apps/worker/tests apps/api/tests

test-unit:
	$(POETRY) run pytest packages/document-model/tests packages/pdf-renderer/tests apps/worker/tests apps/api/tests

test-e2e:
	scripts/e2e_stub_render.sh $(SAMPLE)

lint:
	$(POETRY) run ruff check .

format:
	$(POETRY) run ruff format .

check: lint test

smoke-book:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --force --spread-mode auto-mixed

smoke-ocr:
	BOOK_INPUT=$(BOOK_INPUT) BOOK_OUTPUT=$(BOOK_OUTPUT) OCR_LANG=$(OCR_LANG) bash scripts/smoke_test_ocr.sh

smoke-ocr-verbose:
	BOOK_INPUT=$(BOOK_INPUT) BOOK_OUTPUT=$(BOOK_OUTPUT) OCR_LANG=$(OCR_LANG) VERBOSE=1 bash scripts/smoke_test_ocr.sh

ingest-book:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --spread-mode auto-mixed

ingest-book-force:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --force --spread-mode auto-mixed

ingest-book-verbose:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --verbose --spread-mode auto-mixed

ingest-book-force-verbose:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --force --verbose --spread-mode auto-mixed

ingest-book-auto-mixed:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --spread-mode auto-mixed

ingest-book-auto-mixed-force:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --force --spread-mode auto-mixed

ingest-book-auto-mixed-verbose:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --verbose --spread-mode auto-mixed

ingest-book-ocr:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --ocr --spread-mode auto-mixed

ingest-book-ocr-force:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --ocr --force --spread-mode auto-mixed

ingest-book-ocr-images-force:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --ocr --extract-images --force --spread-mode auto-mixed

inspect-output:
	$(POETRY) run python scripts/inspect_output.py --output $(BOOK_OUTPUT)

full-stack-smoke:
	bash scripts/full_stack_smoke.sh

gemini-review:
	@if [ -z "$(FILE)" ]; then echo "usage: make gemini-review FILE=path/to/file.md"; exit 1; fi
	bash scripts/gemini_review.sh "$(FILE)"

gemini-review-ocr-plan:
	@if [ ! -f "pdf-vault/02-architecture/next-ocr-fix-plan.md" ]; then echo "missing file: pdf-vault/02-architecture/next-ocr-fix-plan.md"; exit 1; fi
	bash scripts/gemini_review.sh pdf-vault/02-architecture/next-ocr-fix-plan.md "Review this OCR fix plan. Focus on missing tests, assumptions, and edge cases."

claude-review:
	@if [ -z "$(FILE)" ]; then echo "usage: make claude-review FILE=path/to/file.md"; exit 1; fi
	bash scripts/claude_review.sh "$(FILE)"

claude-review-ocr-plan:
	@if [ ! -f "pdf-vault/02-architecture/next-ocr-fix-plan.md" ]; then echo "missing file: pdf-vault/02-architecture/next-ocr-fix-plan.md"; exit 1; fi
	bash scripts/claude_review.sh pdf-vault/02-architecture/next-ocr-fix-plan.md "Review this OCR fix plan. Focus on missing tests, assumptions, and edge cases."

opencode-review:
	@if [ -z "$(FILE)" ]; then echo "usage: make opencode-review FILE=path/to/file.md"; exit 1; fi
	bash scripts/opencode_review.sh "$(FILE)"

opencode-review-ocr-plan:
	@if [ ! -f "pdf-vault/02-architecture/next-ocr-fix-plan.md" ]; then echo "missing file: pdf-vault/02-architecture/next-ocr-fix-plan.md"; exit 1; fi
	bash scripts/opencode_review.sh pdf-vault/02-architecture/next-ocr-fix-plan.md "Review this OCR fix plan. Focus on missing tests, assumptions, and edge cases."

ollama-draft:
	@if [ -z "$(FILE)" ]; then echo "usage: make ollama-draft FILE=path/to/file.md"; exit 1; fi
	bash scripts/ollama_doc_draft.sh "$(FILE)"

reviewer-healthcheck:
	@echo "Run this target in your normal shell outside Codex sandbox for representative Gemini/Claude results."
	bash scripts/reviewer_healthcheck.sh
