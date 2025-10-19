from __future__ import annotations


def is_candidate_pdf(name: str | None, path: str | None) -> bool:
    n = (name or "").lower()
    p = (path or "").lower()
    if n == "readme.pdf":
        return False
    if "/book/" in p or p.endswith("/book") or p.startswith("book/"):
        return False
    return n.endswith(".pdf")
