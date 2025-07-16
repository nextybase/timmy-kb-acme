import spacy

try:
    nlp = spacy.load("it_core_news_sm")
except Exception:
    nlp = None
    print("⚠️ spaCy non disponibile.")

def estrai_entita(testo: str) -> list:
    if not nlp:
        return []

    doc = nlp(testo)
    entita = []
    for ent in doc.ents:
        entita.append({
            "valore": ent.text.strip(),
            "tipo": ent.label_,
            "origine": "nlp"
        })
    return entita

def estrai_relazioni(testo: str) -> list:
    # Placeholder relazionale (base): soggetto-verbo-oggetto semplificato
    if not nlp:
        return []

    doc = nlp(testo)
    relazioni = []
    for sent in doc.sents:
        subj = None
        obj = None
        verb = None
        for tok in sent:
            if tok.dep_ in ("nsubj", "nsubj:pass") and subj is None:
                subj = tok.text
            elif tok.dep_ in ("dobj", "obj") and obj is None:
                obj = tok.text
            elif tok.pos_ == "VERB" and verb is None:
                verb = tok.lemma_
        if subj and verb and obj:
            relazioni.append((subj, verb, obj))
    return relazioni

def arricchisci_entita_con_contesto(entita: list, contesto: dict) -> list:
    """Arricchisce entità con tipo/alias basati sul contesto semantico della cartella."""
    mappa = {e.lower(): e for e in contesto.get("entita_rilevanti", [])}
    entita_arricchite = []

    for e in entita:
        valore = e["valore"].lower()
        if valore in mappa:
            e["tipo"] = mappa[valore]  # Sovrascrive tipo se corrisponde
            e["origine"] = "contesto"
        entita_arricchite.append(e)

    return entita_arricchite
