SAMPLE ?= sample.png
BOOK_INPUT ?= book
BOOK_OUTPUT ?= output
PYTHONPATH ?= apps/worker:packages/document-model/src:packages/pdf-renderer/src
POETRY ?= poetry

.PHONY: install up migrate test test-unit test-e2e lint format check stub-render smoke-book ingest-book ingest-book-force ingest-book-verbose ingest-book-force-verbose ingest-book-auto-mixed ingest-book-auto-mixed-force ingest-book-auto-mixed-verbose ingest-book-ocr ingest-book-ocr-force inspect-output full-stack-smoke

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
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --ocr

ingest-book-ocr-force:
	PYTHONPATH=$(PYTHONPATH) $(POETRY) run python -m worker.ingest_book --input $(BOOK_INPUT) --output $(BOOK_OUTPUT) --ocr --force

inspect-output:
	$(POETRY) run python scripts/inspect_output.py --output $(BOOK_OUTPUT)

full-stack-smoke:
	bash scripts/full_stack_smoke.sh
