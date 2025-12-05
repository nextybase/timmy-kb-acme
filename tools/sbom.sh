#!/usr/bin/env bash
set -euo pipefail

OUTPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output)
      OUTPUT="$2"
      shift 2
      ;;
    *)
      echo "Usage: sbom.sh [-o OUTPUT]" >&2
      exit 1
      ;;
  esac
done

if [[ -z "${OUTPUT}" ]]; then
  OUTPUT="sbom.json"
fi

if ! command -v cyclonedx-py >/dev/null 2>&1; then
  echo "cyclonedx-py non trovato: installa con 'pip install cyclonedx-bom'." >&2
  exit 1
fi

echo "Generazione SBOM in ${OUTPUT}"
if ! cyclonedx-py requirements --format json --output "${OUTPUT}" --include-dev --overwrite; then
  echo "Fallback pipdeptree -> cyclonedx" >&2
  if ! command -v pipdeptree >/dev/null 2>&1; then
    echo "pipdeptree non trovato: installa con 'pip install pipdeptree'." >&2
    exit 1
  fi
  pipdeptree --json-tree | cyclonedx-py convert --input-format pipdeptree --output "${OUTPUT}" --overwrite
fi
