#!/usr/bin/env python
# scripts/quick_openai_diag.py
from __future__ import annotations
import os
import sys
from pathlib import Path


def _load_env() -> str:
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
    except Exception:
        return "<python-dotenv non installato>"
    path = find_dotenv(usecwd=True)
    loaded = False
    if path:
        loaded = load_dotenv(path, override=False)
    if not loaded:
        # fallback: repo root
        repo_root = Path(__file__).resolve().parents[1]
        env = repo_root / ".env"
        if env.exists():
            path = str(env)
            loaded = load_dotenv(env, override=False)
    return path or "<non trovato>"


def _normalize_base_url(url: str | None) -> str:
    if not url:
        return ""
    u = url.strip()
    if "://" not in u:
        u = "https://" + u
    if not u.rstrip("/").endswith("/v1"):
        u = u.rstrip("/") + "/v1"
    return u


def main() -> int:
    print("=== OpenAI Diagnostics (v3) ===")
    env_path = _load_env()
    print(f".env: {env_path}")

    try:
        import importlib.metadata as ilm  # py>=3.8

        ver = ilm.version("openai")
    except Exception:
        ver = "<openai non installato>"
    print(f"openai version: {ver}")

    api_key = os.getenv("OPENAI_API_KEY") or ""
    project = os.getenv("OPENAI_PROJECT") or ""
    base_url_env = os.getenv("OPENAI_BASE_URL") or ""
    assistant = os.getenv("OBNEXT_ASSISTANT_ID") or os.getenv("ASSISTANT_ID") or ""

    print(f"OPENAI_API_KEY: {'<settata>' if api_key else '<vuoto>'}")
    print(f"OPENAI_PROJECT: {project or '<vuoto>'}")
    print(f"OPENAI_BASE_URL(raw): {base_url_env or '<vuoto>'}")
    print(f"ASSISTANT_ID/OBNEXT_ASSISTANT_ID: {assistant or '<vuoto>'}")

    # Normalizza URL per evidenziare errori comuni
    normalized = _normalize_base_url(base_url_env) if base_url_env else "https://api.openai.com/v1"
    print(f"OPENAI_BASE_URL(effettiva): {normalized}")

    if not api_key:
        print(
            "\nERRORE: client non inizializzato: " "manca OPENAI_API_KEY (aggiungila in .env o esportala in ambiente)."
        )
        return 2

    # Prova di rete minimale (Responses) senza side-effect di scrittura
    try:
        from openai import OpenAI  # type: ignore

        client = OpenAI(base_url=normalized, api_key=api_key, project=project or None)
        # chiamata “no-op” (elenca modelli). Se la rete è rotta, esplode qui.
        _ = client.models.list()
        print("Ping SDK: OK (models.list)")
        return 0
    except Exception as e:
        print(f"ERRORE: ping fallito → {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
