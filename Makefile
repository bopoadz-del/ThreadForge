.PHONY: fetch-fixtures test lint typecheck release

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

# gate (ruff/mypy/pytest/openapi + A01–A29) → tag v1.0.1 → push → acceptance 30/30
# A30 needs the tag on origin, so the 30/30 run is after push.
release:
	python scripts/release_gate.py --tag v1.0.1
	git push origin HEAD
	git push origin v1.0.1
	python scripts/acceptance.py
