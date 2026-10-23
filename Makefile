.PHONY: install format-check format-fix lint-check lint-fix type-check test eval check-all

install:
	uv sync

format-check:
	uv run ruff format --check

format-fix:
	uv run ruff format

lint-check:
	uv run ruff check

lint-fix:
	uv run ruff check --fix

type-check:
	uv run ty check

test:
	uv run pytest

eval:
	uv run hci eval

check-all: format-check lint-check type-check test
