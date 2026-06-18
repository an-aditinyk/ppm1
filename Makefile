.PHONY: check lint type arch test update-golden install

check: lint type arch test

lint:
	ruff check .
	ruff format --check .

type:
	mypy src

arch:
	lint-imports

test:
	pytest

update-golden:
	UPDATE_GOLDEN=1 pytest tests/golden -q

install:
	uv pip install -e ".[dev]"
