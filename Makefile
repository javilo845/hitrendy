.PHONY: validate demo demo-reset test-demo graphify install dev test lint format

validate:
	python scripts/validate_package.py

test-demo:
	cd demo && python -m pytest -q

demo:
	cd demo && uvicorn app:app --reload

demo-reset:
	python scripts/reset_demo_database.py --confirm

install:
	npm ci
	python -m pip install -r starter/backend/requirements-dev.txt

dev:
	npm run dev

test:
	npm run web:test
	PYTHONPATH=starter/backend python -m pytest starter/backend/tests

lint:
	npm run web:typecheck
	npm run web:lint

format:
	npx prettier --write "starter/web/**/*.{ts,tsx,css,json}"
	python -m ruff format starter/backend/

graphify:
	@echo "Run /graphify . from a supported coding assistant after installing graphifyy"
