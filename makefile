# Usa SEMPRE l'ambiente già attivo (venv/conda)
PY ?= python3
PIP := $(PY) -m pip

.PHONY: env-check install pre-commit lint type type-pyright test fmt fmt-check ci qa-safe ci-safe

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

type-pyright: env-check
	@if command -v pyright >/dev/null 2>&1; then \
	  pyright; \
	else \
	  npx -y pyright; \
	fi

test: env-check
	@pytest -ra

fmt: env-check
	@black src tests

fmt-check: env-check
	@black --check src tests

ci: fmt-check lint type test

# Esegue linters/type-check solo se disponibili nel PATH, altrimenti salta (degrado pulito)
qa-safe:
	@if command -v black >/dev/null 2>&1; then \
	  echo "[qa-safe] black --check"; black --check src tests; \
	else \
	  echo "[qa-safe] black non installato: skip"; \
	fi
	@if command -v flake8 >/dev/null 2>&1; then \
	  echo "[qa-safe] flake8"; flake8 src tests; \
	else \
	  echo "[qa-safe] flake8 non installato: skip"; \
	fi
	@if command -v mypy >/dev/null 2>&1; then \
	  echo "[qa-safe] mypy"; mypy src; \
	else \
	  echo "[qa-safe] mypy non installato: skip"; \
	fi

# Variante completa che include i test, ma sempre in modo degradabile
ci-safe: qa-safe
	@if command -v pytest >/dev/null 2>&1; then \
	  echo "[ci-safe] pytest"; pytest -ra; \
	else \
	  echo "[ci-safe] pytest non installato: skip"; \
	fi
