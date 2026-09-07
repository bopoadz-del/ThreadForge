.PHONY: fetch-fixtures test lint typecheck

fetch-fixtures:
	@mkdir -p fixtures/public/cache
	@echo "Fetching public DEXPI/Proteus assets (network once)..."
	@python scripts/fetch_public_fixtures.py || true

test:
	python -m pytest -q

lint:
	ruff check src tests

typecheck:
	mypy --strict src/threadforge

dist-zip:
	@mkdir -p dist
	@git archive --format=zip --prefix=threadforge/ -o dist/threadforge-drop2.zip HEAD
	@echo "Wrote dist/threadforge-drop2.zip"
