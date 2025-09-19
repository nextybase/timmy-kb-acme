# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/constants.py
"""Single Source of Truth (SSoT) per i **nomi di directory/file** e per alcuni **MIME type** usati
in tutta la pipeline Timmy-KB.

Perché qui:
- Riduce i "magic string" dispersi nel codice.
- Consente modifiche architetturali controllate (es. rinominare `output/` o `book/`).
- Mantiene coerenza tra orchestratori, adapters e moduli `pipeline.*`.

Note uso:
- I chiamanti devono **importare da qui** invece di hardcodare stringhe.
- Cambiare un valore richiede verifiche d’impatto (es. path già persistiti su disco/Drive).
"""

# 📂 Directory e file standard
OUTPUT_DIR_NAME = "output"
LOGS_DIR_NAME = "logs"
CONFIG_DIR_NAME = "config"
RAW_DIR_NAME = "raw"
BOOK_DIR_NAME = "book"
SEMANTIC_DIR_NAME = "semantic"  # aggiunto per completezza (molti moduli usano 'semantic/')

CONFIG_FILE_NAME = "config.yaml"
SEMANTIC_MAPPING_FILE = "semantic_mapping.yaml"

# 🪵 Logging
LOG_FILE_NAME = "onboarding.log"  # usato dagli orchestratori come nome file log

# 📄 Suffissi di backup e temporanei
BACKUP_SUFFIX = ".bak"
TMP_SUFFIX = ".tmp"

# 📌 Base dir name (eventuali validazioni path)
BASE_DIR_NAME = "."

# 📦 Google Drive MIME Types
GDRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
GDRIVE_FILE_MIME = "application/vnd.google-apps.file"  # compat; poco usato

# 📄 MIME Types generici
PDF_MIME_TYPE = "application/pdf"

# 📄 File tipici di GitBook/HonKit
BOOK_JSON_NAME = "book.json"
PACKAGE_JSON_NAME = "package.json"
SUMMARY_MD_NAME = "SUMMARY.md"
README_MD_NAME = "README.md"

# 🐙 Git/GitHub
REPO_NAME_PREFIX = "timmy-kb-"
GIT_COMMIT_USER_NAME = "Timmy KB"
GIT_COMMIT_USER_EMAIL = "kb+noreply@local"
# Chiavi d'ambiente da cui risolvere il branch di default (in ordine di priorità)
DEFAULT_GIT_BRANCH_ENV_KEYS = ("GIT_DEFAULT_BRANCH", "GITHUB_BRANCH")
DEFAULT_PREVIEW_PORT = 4000

# 📚 HonKit/GitBook Preview
HONKIT_DOCKER_IMAGE = "honkit/honkit"
PREVIEW_DEFAULT_PORT = 4000
HONKIT_CONTAINER_NAME_PREFIX = "honkit_preview"

# ⚙️ Parametri di performance (tuning “soft”)
# I moduli li possono usare come default, lasciando override da CLI/env.
MAX_CONCURRENCY = 4  # Concorrenza consigliata per job a grana grossa
SKIP_IF_UNCHANGED = True  # Abilita skip quando input non è cambiato

__all__ = [
    # dir/file
    "OUTPUT_DIR_NAME",
    "LOGS_DIR_NAME",
    "CONFIG_DIR_NAME",
    "RAW_DIR_NAME",
    "BOOK_DIR_NAME",
    "SEMANTIC_DIR_NAME",
    "CONFIG_FILE_NAME",
    "SEMANTIC_MAPPING_FILE",
    "LOG_FILE_NAME",
    "BACKUP_SUFFIX",
    "TMP_SUFFIX",
    "BASE_DIR_NAME",
    # mime
    "GDRIVE_FOLDER_MIME",
    "GDRIVE_FILE_MIME",
    "PDF_MIME_TYPE",
    # book/honkit
    "BOOK_JSON_NAME",
    "PACKAGE_JSON_NAME",
    "SUMMARY_MD_NAME",
    "README_MD_NAME",
    # git
    "REPO_NAME_PREFIX",
    "GIT_COMMIT_USER_NAME",
    "GIT_COMMIT_USER_EMAIL",
    "DEFAULT_GIT_BRANCH_ENV_KEYS",
    # preview
    "HONKIT_DOCKER_IMAGE",
    "PREVIEW_DEFAULT_PORT",
    "HONKIT_CONTAINER_NAME_PREFIX",
    # perf
    "MAX_CONCURRENCY",
    "SKIP_IF_UNCHANGED",
]
