# SPDX-License-Identifier: GPL-3.0-or-later
# src/nlp/nlp_keywords.py
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from typing import Any, DefaultDict, Dict, Iterable, List, Tuple, TypedDict


class ClusterGroup(TypedDict):
    canonical: str
    synonyms: List[str]
    members: List[Tuple[str, float]]


def _require(module: str, help_msg: str) -> Any:
    try:
        return __import__(module)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(help_msg) from e


def _as_str(val: Any) -> str:
    """Converte in stringa in modo robusto (utile per API che tipizzano come 'object')."""
    if isinstance(val, str):
        return val
    if isinstance(val, (bytes, bytearray)):
        try:
            return val.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    return "" if val is None else str(val)


def extract_text_from_pdf(path: str) -> str:
    """Legge tutto il testo dal PDF usando pypdf; segnala esplicitamente eventuali problemi."""
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Il pacchetto 'pypdf' è richiesto per leggere i PDF.") from exc

    try:
        reader = PdfReader(path)
    except Exception as exc:
        raise RuntimeError(f"Impossibile aprire il PDF {path} con pypdf: verifica il file.") from exc

    collected: list[str] = []
    for index, page in enumerate(getattr(reader, "pages", []) or []):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise RuntimeError(f"Estrazione testo fallita nella pagina {index} del PDF {path}.") from exc
        if text:
            collected.append(text)

    if not collected:
        raise RuntimeError(f"Nessun testo estratto dal PDF {path}.")
    return "\n".join(collected)


@lru_cache(maxsize=4)
def _load_spacy(lang: str = "it") -> Any:
    """Carica spaCy richiedendo i modelli principali (md)."""
    try:
        import spacy
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare spaCy: pip install spacy e il relativo modello.") from e

    model = "it_core_news_md" if lang.startswith("it") else "en_core_web_md"
    try:
        return spacy.load(model)
    except Exception as e:
        raise RuntimeError(
            f"Impossibile caricare il modello spaCy '{model}'. Esegui 'python -m spacy download {model}'."
        ) from e


@lru_cache(maxsize=2)
def _require_sent_transformer(model_name: str = "all-MiniLM-L6-v2") -> Any:
    """
    Carica SentenceTransformer, riducendo le importazioni ripetute.
    """
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare sentence-transformers: pip install sentence-transformers") from e
    return SentenceTransformer(model_name)


def normalize_phrase(phrase: str) -> str:
    """
    Normalize a string (lowercase, strip accents, collapse whitespaces, remove punctuation).

    Guard rail: conserva i caratteri alfanumerici e poche separazioni (/, -, _).
    """
    if not phrase:
        return ""
    # Normalizza unicode per rimuovere accenti
    nfkd = unicodedata.normalize("NFKD", phrase)
    no_accents = "".join([c for c in nfkd if not unicodedata.combining(c)])
    # Minuscolo + normalizzazione spazi
    lowered = no_accents.lower()
    cleaned = re.sub(r"[^a-z0-9\\/_\\-\\s]", " ", lowered)
    collapsed = re.sub(r"\\s+", " ", cleaned).strip()
    return collapsed


def clean_candidates(text: str) -> List[str]:
    """
    Genera candidati basati su spaCy (lemma/entità) e heuristica regex leggera.

    Rimuove stopword e termini troppo brevi.
    """
    nlp = _load_spacy("it")
    doc = nlp(text)
    stopwords = nlp.Defaults.stop_words

    candidates: set[str] = set()

    # 1) Named entities
    for ent in getattr(doc, "ents", []) or []:
        normalized = normalize_phrase(ent.text)
        if len(normalized) >= 3:
            candidates.add(normalized)

    # 2) Lemmi di sostantivi e aggettivi
    for token in doc:
        if token.pos_ in {"NOUN", "PROPN", "ADJ"}:
            lemma = normalize_phrase(token.lemma_)
            if lemma and lemma not in stopwords and len(lemma) >= 3:
                candidates.add(lemma)

    # 3) Heuristica regex per pattern come "progetto X", "linee guida", ecc.
    regex_candidates = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9 /_-]{2,}", text)
    for cand in regex_candidates:
        normalized = normalize_phrase(cand)
        if len(normalized) >= 3 and normalized not in stopwords:
            candidates.add(normalized)

    return sorted(candidates)


def spacy_candidates(text: str) -> List[str]:
    """Alias di convenienza verso `clean_candidates` (firma invariata)."""
    return clean_candidates(text)


def yake_scores(text: str, top_k: int = 20) -> List[Tuple[str, float]]:
    """
    Calcola score YAKE! (return sorted list).
    """
    yake_mod = _require(
        "yake",
        "Installare YAKE: pip install yake",
    )
    kw_extractor = yake_mod.KeywordExtractor(lan="it", n=3, top=top_k, features=None)
    scores: List[Tuple[str, float]] = []
    for kw, score in kw_extractor.extract_keywords(text):
        normalized = normalize_phrase(kw)
        if normalized:
            scores.append((normalized, float(score)))
    return scores


def keybert_scores(text: str, top_k: int = 20) -> List[Tuple[str, float]]:
    """
    Calcola score KeyBERT (cosine similarity embeddings).
    """
    keybert_mod = _require(
        "keybert",
        "Installare keybert: pip install keybert",
    )
    kw_model = keybert_mod.KeyBERT()
    candidates = kw_model.extract_keywords(
        text,
        keyphrase_ngram_range=(1, 3),
        stop_words="italian",
        top_n=top_k,
    )
    pairs = []
    for kw, score in candidates:
        normalized = normalize_phrase(kw)
        if normalized:
            pairs.append((normalized, float(score)))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:top_k]


def fuse_and_dedup(
    text: str,
    cand_spacy: Iterable[str],
    sc_yake: Iterable[Tuple[str, float]],
    sc_keybert: Iterable[Tuple[str, float]],
    w_spacy: float = 0.2,
    w_yake: float = 0.4,
    w_keybert: float = 0.4,
    min_len: int = 3,
    max_len: int = 80,
) -> List[Tuple[str, float]]:
    """Unifica le sorgenti e calcola uno score ensemble."""

    def norm_ok(s: str) -> bool:
        return bool(min_len <= len(s) <= max_len and bool(re.search(r"[a-z0-9]", s)))

    # Normalizza chiavi, ma conserva la forma più frequente come display
    spacy_norm = [normalize_phrase(s) for s in cand_spacy if s]
    spacy_set = set(spacy_norm)

    def _to_norm_map(items: Iterable[Tuple[str, float]]) -> Dict[str, float]:
        m: Dict[str, float] = {}
        for p, sc in items:
            n = normalize_phrase(p)
            m[n] = max(m.get(n, 0.0), float(sc))
        return m

    yake_map: Dict[str, float] = _to_norm_map(sc_yake)
    kb_map: Dict[str, float] = _to_norm_map(sc_keybert)

    # Conta frequenza delle forme originali per ciascun normalizzato
    forms: DefaultDict[str, Counter[str]] = defaultdict(Counter)
    for s in cand_spacy:
        n = normalize_phrase(s)
        forms[n][s] += 1
    for p, _ in sc_yake:
        n = normalize_phrase(p)
        forms[n][p] += 1
    for p, _ in sc_keybert:
        n = normalize_phrase(p)
        forms[n][p] += 1

    all_norm = set(spacy_set) | set(yake_map.keys()) | set(kb_map.keys())
    out_norm: Dict[str, float] = {}
    for n in all_norm:
        if not norm_ok(n):
            continue
        score = 0.0
        if n in spacy_set:
            score += w_spacy * 1.0
        if n in yake_map:
            score += w_yake * float(yake_map[n])
        if n in kb_map:
            score += w_keybert * float(kb_map[n])
        prev = out_norm.get(n)
        out_norm[n] = max(prev, score) if prev is not None else score

    # Scegli display come forma più frequente per ciascun normalizzato
    out: List[Tuple[str, float]] = []
    for n, sc in out_norm.items():
        if forms.get(n):
            disp = forms[n].most_common(1)[0][0]
        else:
            disp = n
        out.append((disp, sc))
    return out


def cluster_synonyms(
    phrases_scores: List[Tuple[str, float]],
    model_name: str = "all-MiniLM-L6-v2",
    sim_thr: float = 0.82,
) -> List[ClusterGroup]:
    """Clustra per embedding basandosi su soglia di similarità (connected components)."""
    try:
        _ = __import__("sentence_transformers")
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare sentence-transformers") from e
    try:
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare scikit-learn") from e

    if not phrases_scores:
        return []
    # Normalizza prima del clustering
    phrases: List[str] = [normalize_phrase(p) for p, _ in phrases_scores]
    scores: Dict[str, float] = {normalize_phrase(p): float(s) for p, s in phrases_scores}
    model = _require_sent_transformer(model_name)
    emb = model.encode(phrases, normalize_embeddings=True)
    sim = cosine_similarity(emb, emb)

    n = len(phrases)
    visited: List[bool] = [False] * n
    clusters: List[List[int]] = []

    for i in range(n):
        if visited[i]:
            continue
        comp: List[int] = []
        stack: List[int] = [i]
        visited[i] = True
        while stack:
            j = stack.pop()
            comp.append(j)
            for k in range(n):
                if not visited[k] and sim[j, k] >= sim_thr:
                    visited[k] = True
                    stack.append(k)
        clusters.append(comp)

    out: List[ClusterGroup] = []
    for comp in clusters:
        members: List[Tuple[str, float]] = [(phrases[idx], scores.get(phrases[idx], 0.0)) for idx in comp]
        # canonical: frase con score più alto
        canonical = max(members, key=lambda x: x[1])[0]
        synonyms = [p for p, _ in members if p != canonical]
        out.append({"canonical": canonical, "synonyms": synonyms, "members": members})
    return out


def topn_by_folder(doc_items: List[Tuple[str, float]], k: int = 30) -> List[Tuple[str, float]]:
    """Ordina per score desc e ritorna i primi k."""
    return sorted(doc_items, key=lambda x: x[1], reverse=True)[:k]
