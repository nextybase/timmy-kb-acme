# SPDX-License-Identifier: GPL-3.0-or-later
# src/nlp/nlp_keywords.py
from __future__ import annotations

import re
import unicodedata
from typing import Any, DefaultDict, Dict, Iterable, List, Tuple, TypedDict, Optional
from collections import Counter, defaultdict
from functools import lru_cache


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
    """
    Legge TUTTO il testo dal PDF.
    Strategia:
      - prova con pypdf, se non disponibile fa fallback su PyMuPDF (fitz).
    Se entrambe mancano, alza RuntimeError con istruzioni d'installazione.
    """
    # Tentativo 1: pypdf
    PdfReader = None
    try:
        from pypdf import PdfReader as _PdfReader  # type: ignore

        PdfReader = _PdfReader
    except Exception:
        PdfReader = None

    if PdfReader is not None:
        try:
            reader = PdfReader(path)  # type: ignore[misc]
            texts: List[str] = []
            for p in getattr(reader, "pages", []) or []:
                try:
                    t: str = p.extract_text() or ""
                except Exception:
                    t = ""
                if t:
                    texts.append(t)
            return "\n".join(texts)
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Errore lettura PDF con pypdf; assicurarsi che il file sia valido o usa PyMuPDF"
            ) from e

    # Tentativo 2: PyMuPDF (fitz)
    try:
        import fitz  # PyMuPDF
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare pypdf oppure PyMuPDF (fitz)") from e

    try:
        doc = fitz.open(path)
        texts: List[str] = []
        try:
            for page in doc:
                try:
                    # Preferisci la modalità esplicita "text" per coerenza tra versioni;
                    # se non supportata, ricadi su chiamata senza argomenti o sulla vecchia API.
                    getter = getattr(page, "get_text", None)
                    if callable(getter):
                        try:
                            t: str = _as_str(getter("text"))
                        except TypeError:
                            try:
                                t = _as_str(getter())
                            except Exception:
                                t = ""
                    else:
                        getter_old = getattr(page, "getText", None)  # compat vecchie versioni
                        if callable(getter_old):
                            try:
                                t = _as_str(getter_old("text"))
                            except TypeError:
                                try:
                                    t = _as_str(getter_old())
                                except Exception:
                                    t = ""
                        else:
                            t = ""
                except Exception:
                    t = ""
                if t:
                    texts.append(t)
        finally:
            try:
                doc.close()
            except Exception:
                pass
        return "\n".join(texts)
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Errore lettura PDF; assicurarsi che il file sia valido e che PyMuPDF funzioni"
        ) from e


@lru_cache(maxsize=4)
def _load_spacy(lang: str = "it") -> Any:
    """
    Carica spaCy con fallback:
      - it: prima 'it_core_news_md', poi 'it_core_news_sm'
      - en: prima 'en_core_web_md', poi 'en_core_web_sm'
    """
    try:
        import spacy
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "Installare spaCy: pip install spacy e il modello (es. it_core_news_sm)"
        ) from e

    if lang.startswith("it"):
        models = ["it_core_news_md", "it_core_news_sm"]
    else:
        models = ["en_core_web_md", "en_core_web_sm"]

    last_err: Optional[Exception] = None
    for model in models:
        try:
            return spacy.load(model)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(
        f"Modello spaCy mancante: installa uno tra {', '.join(models)} "
        f"(es. python -m spacy download {models[-1]})"
    ) from last_err


def normalize_phrase(s: str) -> str:
    """Normalizza frasi per matching robusto:
    - lower
    - NFKD + rimozione diacritici
    - sostituzione '-' con spazio
    - collapse whitespace
    - strip
    """
    s = (s or "").lower().replace("-", " ")
    # Unicode normalize + strip diacritici
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def spacy_candidates(text: str, lang: str = "it", max_ngram: int = 4) -> List[str]:
    """
    Estrae noun-chunks e proper-nouns (1-4 token) con spaCy.
    Normalizza (lower, strip punteggiatura), filtra stopword e token troppo corti.
    Ritorna lista di candidate (non dedup).
    """
    if not text:
        return []
    nlp = _load_spacy(lang)
    doc = nlp(text)
    out: List[str] = []
    # noun chunks
    for nc in getattr(doc, "noun_chunks", []) or []:
        toks = [t for t in nc if not (t.is_punct or t.is_space)]
        if 1 <= len(toks) <= max_ngram:
            s = nc.text.strip()
            if len(s) >= 3:
                out.append(s)
    # proper nouns (and simple n-grams up to max_ngram)
    tokens = [t for t in doc if not (t.is_punct or t.is_space)]
    for i in range(len(tokens)):
        # single proper noun or noun
        if tokens[i].pos_ in {"PROPN", "NOUN"} and not tokens[i].is_stop:
            s = tokens[i].text.strip()
            if len(s) >= 3:
                out.append(s)
        # small n-grams
        for n in range(2, max_ngram + 1):
            j = i + n
            if j <= len(tokens):
                span = tokens[i:j]
                if any(t.is_stop for t in span):
                    continue
                s = " ".join(t.text for t in span).strip()
                if len(s) >= 3:
                    out.append(s)
    return out


def yake_scores(text: str, top_k: int = 30, lang: str = "it") -> List[Tuple[str, float]]:
    """
    Usa YAKE per estrarre (phrase, score) [score più basso = migliore].
    Converti in punteggio normalizzato 0..1 dove 1 è migliore (es. score_yake = 1 / (1 + raw)).
    """
    try:
        import yake
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare yake") from e

    kw_extractor = yake.KeywordExtractor(lan=lang[:2], n=1, top=top_k)
    raw = kw_extractor.extract_keywords(text or "")
    out: List[Tuple[str, float]] = []
    for phrase, score in raw:
        s = 1.0 / (1.0 + float(score))
        out.append((phrase, s))
    return out


@lru_cache(maxsize=8)
def _load_st_model(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def keybert_scores(
    text: str,
    candidates: Iterable[str],
    model_name: str = "all-MiniLM-L6-v2",
    top_k: int = 30,
) -> List[Tuple[str, float]]:
    """
    Usa SentenceTransformer per embed del documento e dei candidati; score = cos(doc, cand).
    Ritorna lista (phrase, score in 0..1).
    """
    try:
        _ = __import__("sentence_transformers")
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare sentence-transformers") from e
    try:
        from sklearn.metrics.pairwise import cosine_similarity
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Installare scikit-learn") from e

    model = _load_st_model(model_name)
    cands = list({c for c in candidates if c and len(c) >= 3})
    if not cands:
        return []
    emb_doc = model.encode([text or ""], normalize_embeddings=True)
    emb_c = model.encode(cands, normalize_embeddings=True)
    sims = cosine_similarity(emb_c, emb_doc)[:, 0]
    pairs: List[Tuple[str, float]] = list(zip(cands, sims.tolist()))
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
    """
    Unifica le sorgenti e calcola uno score ensemble.
    """

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
    """
    Clustra per embedding basandosi su soglia di similarità (connected components).
    """
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
    model = _load_st_model(model_name)
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
        members: List[Tuple[str, float]] = [
            (phrases[idx], scores.get(phrases[idx], 0.0)) for idx in comp
        ]
        # canonical: frase con score più alto
        canonical = max(members, key=lambda x: x[1])[0]
        synonyms = [p for p, _ in members if p != canonical]
        out.append({"canonical": canonical, "synonyms": synonyms, "members": members})
    return out


def topn_by_folder(doc_items: List[Tuple[str, float]], k: int = 30) -> List[Tuple[str, float]]:
    """Ordina per score desc e ritorna i primi k."""
    return sorted(doc_items, key=lambda x: x[1], reverse=True)[:k]
