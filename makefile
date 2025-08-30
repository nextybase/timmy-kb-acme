# Usa SEMPRE l'ambiente già attivo (venv/conda)
PY ?= python3
PIP := $(PY) -m pip

.PHONY: env-check install pre-commit lint type test fmt fmt-check ci

env-check:
	@if [ -n "$$ALLOW_GLOBAL" ]; then \
	  echo "⚠️  Skipping env check (ALLOW_GLOBAL=1)"; exit 0; \
	fi; \
	if [ -z "$$VIRTUAL_ENV" ] && [ -z "$$CONDA_PREFIX" ]; then \
	  echo "✖ Nessun ambiente virtuale attivo. Attivalo (venv/conda) oppure esegui con ALLOW_GLOBAL=1."; \
	  exit 1; \
	fi

install: env-check
	@$(PIP) install -U black flake8 flake8-bugbear flake8-annotations flake8-bandit flake8-print mypy pytest pytest-cov pre-commit

pre-commit: env-check
	@pre-commit install --hook-type pre-commit --hook-type pre-push

lint: env-check
	@flake8 src tests

type: env-check
	@mypy src

test: env-check
	@pytest -ra

fmt: env-check
	@black src tests

fmt-check: env-check
	@black --check src tests

ci: fmt-check lint type test
