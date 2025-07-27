"""
Utils generici – funzioni di validazione e helper trasversali.
Le funzioni qui raccolte sono pensate per essere riusate tra orchestratori e moduli diversi,
evitando duplicazioni e facilitando la manutenzione.
"""

import re

def is_valid_slug(slug: str) -> bool:
    """
    Verifica che lo slug sia conforme a [a-z0-9-], senza caratteri strani o path traversali.
    Utile per validare identificativi di clienti, repo, cartelle output, ecc.
    """
    if not slug:
        return False
    return re.fullmatch(r"[a-z0-9-]+", slug) is not None
