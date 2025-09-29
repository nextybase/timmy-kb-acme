param([ValidateSet("Install","CI","CILite")]$Task="CI")
function Install { pip install -e .; pip install types-PyYAML }
function CI { isort --check-only src tests; black --check src tests; ruff check src tests; mypy -p pipeline -p ui -p semantic -p adapters -p tools; pytest -ra }
function CILite {
  isort --check-only src tests
  black --check src tests
  ruff check src tests
  pytest -k 'unit or content_utils' -ra
  # mypy -p ui  # opzionale: attiva se vuoi includere mypy veloce su ui
}
Invoke-Expression $Task
