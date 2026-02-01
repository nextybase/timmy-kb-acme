# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/backend.py
"""Re-export delle API pubbliche pipeline/semantic usate dalla UI.

Uso: importare da qui per evitare duplicare wrapper e mantenere le firme allineate al backend.
"""

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, to_kebab, to_kebab_soft

__all__ = [
    "safe_write_text",
    "ensure_within_and_resolve",
    "to_kebab",
    "to_kebab_soft",
]
