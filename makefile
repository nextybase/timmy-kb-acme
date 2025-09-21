# Usa SEMPRE l'ambiente già attivo (venv/conda)
PY ?= python3
PIP := $(PY) -m pip

.PHONY: env-check install pre-commit lint type type-pyright test test-vscode fmt fmt-check ci qa-safe ci-safe bench

env-check:
	@if [ -n "$$ALLOW_GLOBAL" ]; then \
	  echo "⚠️  Skipping env check (ALLOW_GLOBAL=1)"; exit 0; \
	fi; \
	if [ -z "$$VIRTUAL_ENV" ] && [ -z "$$CONDA_PREFIX" ]; then \
	  echo "✖ Nessun ambiente virtuale attivo. Attivalo (venv/conda) oppure esegui con ALLOW_GLOBAL=1."; \
	  exit 1; \
	fi

install: env-check
	@$(PIP) install -U black isort ruff mypy pytest pytest-cov pre-commit

pre-commit: env-check
	@pre-commit install --hook-type pre-commit --hook-type pre-push

lint: env-check
	@ruff check src tests

type: env-check
	@mypy src

type-pyright: env-check
	@if command -v pyright >/dev/null 2>&1; then \
	  pyright; \
	else \
	  npx -y pyright; \
	fi

test: env-check
	@$(PY) -m pytest -ra

# Esegue pytest usando esplicitamente il venv locale (se presente)
test-vscode:
	@if [ -x "venv/Scripts/python.exe" ]; then \
	  "venv/Scripts/python.exe" -m pytest -ra; \
	elif [ -n "$$VIRTUAL_ENV" ]; then \
	  $(PY) -m pytest -ra; \
	else \
	  echo "[test-vscode] Nessun venv trovato. Attivalo (./venv) o usa: py -3.11 -m pytest -ra"; exit 1; \
	fi

fmt: env-check
	@isort src tests
	@black src tests

fmt-check: env-check
	@isort --check-only src tests
	@black --check src tests

ci: fmt-check lint type test

# Esegue linters/type-check solo se disponibili nel PATH, altrimenti salta (degrado pulito)
qa-safe:
	@if command -v isort >/dev/null 2>&1; then \
	  echo "[qa-safe] isort --check-only"; isort --check-only src tests; \
	else \
	  echo "[qa-safe] isort non installato: skip"; \
	fi
	@if command -v black >/dev/null 2>&1; then \
	  echo "[qa-safe] black --check"; black --check src tests; \
	else \
	  echo "[qa-safe] black non installato: skip"; \
	fi
	@if command -v ruff >/dev/null 2>&1; then \
	  echo "[qa-safe] ruff check"; ruff check src tests; \
	else \
	  echo "[qa-safe] ruff non installato: skip"; \
	fi
	@if command -v mypy >/dev/null 2>&1; then \
	  echo "[qa-safe] mypy"; mypy src; \
	else \
	  echo "[qa-safe] mypy non installato: skip"; \
	fi

# Variante completa che include i test, ma sempre in modo degradabile
sbom: env-check
\t@./tools/sbom.sh --output sbom.json

sbom: env-check
\t@./tools/sbom.sh --output sbom.json

ci-safe: qa-safe
	@if command -v pytest >/dev/null 2>&1; then \
	  echo "[ci-safe] pytest"; pytest -ra; \
	else \
	  echo "[ci-safe] pytest non installato: skip"; \
	fi

# Benchmark leggerezza normalizzazione embeddings (retriever/semantic)
bench: env-check
	@$(PY) -m scripts.bench_embeddings_normalization
