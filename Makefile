.PHONY: help install install-frontend dev api web test lint format migrate revision seed check frontend-build compose-validate

VENV_PY := backend/.venv/Scripts/python.exe
ifeq ($(OS),)
VENV_PY := backend/.venv/bin/python
endif

help:
	@echo "install           install backend (venv) and frontend dependencies"
	@echo "api               run the API on :8000 (demo mode)"
	@echo "web               run the frontend on :3000"
	@echo "test              backend test suite"
	@echo "lint              ruff over backend + tests"
	@echo "migrate           alembic upgrade head"
	@echo "revision m=...    alembic autogenerate a migration"
	@echo "seed              load demo fixtures into the database"
	@echo "check             full PHASE gate: lint, tests, typecheck, build"

install:
	python -m venv backend/.venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r backend/requirements-dev.txt
	cd frontend && npm install

api:
	cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

web:
	cd frontend && npm run dev

test:
	$(VENV_PY) -m pytest

lint:
	$(VENV_PY) -m ruff check backend tests scripts

format:
	$(VENV_PY) -m ruff format backend tests scripts

migrate:
	cd backend && .venv/Scripts/python -m alembic upgrade head

revision:
	cd backend && .venv/Scripts/python -m alembic revision --autogenerate -m "$(m)"

seed:
	$(VENV_PY) scripts/seed_demo.py --force

frontend-build:
	cd frontend && npm run typecheck && npm run build

compose-validate:
	$(VENV_PY) scripts/validate_compose.py

check: lint test frontend-build compose-validate
	$(VENV_PY) scripts/check_phase1.py
