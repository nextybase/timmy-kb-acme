# Guida Utente – Timmy-KB

Questa guida ti accompagna passo-passo nell’uso di **Timmy-KB**, dalla configurazione iniziale all’esecuzione della pipeline, illustrando tutte le interazioni previste.

---

## 📋 Prerequisiti

- **Python** 3.9 o superiore
- **Poetry** o **pip** installati
- Accesso al repository GitHub
- File di configurazione `.env` e YAML corretti
- Accesso al Google Drive di progetto (per caricamento PDF)

---

## ⚡ Installazione

1. **Clona il repository**
   ```bash
   git clone https://github.com/nextybase/timmy-kb-acme.git
   cd timmy-kb-acme
   ```
2. **Installa le dipendenze**
   ```bash
   poetry install
   # oppure
   pip install -r requirements.txt
   ```
3. **Configura variabili ambiente**
   - Crea un file `.env` nella root del progetto con le variabili necessarie (es. credenziali API, token GitHub, percorso Google Drive)
   - Assicurati che i file YAML in `config/` siano corretti e completi

---

## ▶️ Esecuzione della pipeline (interattiva e in due fasi)

La pipeline Timmy-KB si esegue tipicamente in **due fasi**: `pre_onboarding` e `onboarding_full`, entrambe in modalità interattiva.

### 1. Pre-Onboarding

Questa fase prepara l’ambiente e genera le configurazioni iniziali.

```bash
py src/pre_onboarding.py
```

Durante questa fase ti verrà chiesto di:

- Inserire lo **slug** del progetto
- Inserire il **nome reale del cliente**

### 2. Popolamento cartelle Google Drive

Prima di eseguire `onboarding_full`, **carica i file PDF** nella cartella dedicata del Google Drive indicata in configurazione (`drive/pdf_input`). Questa cartella è strutturata in sottodirectory tematiche pensate per una lettura semantica ottimale dei contenuti: ogni tipologia di documento (manuali, schede tecniche, presentazioni, ecc.) ha la propria posizione specifica, così da facilitare il parsing e l’analisi durante l’elaborazione. I documenti caricati in queste cartelle saranno la base per la generazione della knowledge base.

### 3. Onboarding Full

Questa fase esegue l’intero flusso di elaborazione, arricchimento semantico, validazione, generazione e pubblicazione.

```bash
py src/onboarding_full.py
```

Durante l’esecuzione interattiva:

1. Il sistema elabora i documenti caricati, applicando algoritmi di **arricchimento semantico** (estrazione keyword, tagging tematico, normalizzazione dei contenuti) per migliorarne la fruibilità e la ricercabilità.
2. Genera la **KB in anteprima** completa di frontmatter YAML, link interni coerenti e struttura navigabile.
3. Avvia una **Preview Docker** tramite container Honkit, che ti permette di navigare la KB in locale e verificare aspetto, struttura e correttezza semantica.
4. Una volta completato il controllo, premi **INVIO** per confermare e proseguire.
5. Ti verrà chiesto se procedere con il **push su GitHub**:
   - Se confermi, il sistema pubblicherà la KB sul branch di destinazione.
   - In caso contrario, la pipeline si fermerà mantenendo i file generati in locale.

---

## 📂 Output finale

Al termine della procedura, l’output generato sarà disponibile in `output/` e comprenderà:

- **Markdown arricchiti semanticamente**: file `.md` con frontmatter YAML, keyword, tag e metadata ottimizzati.
- **File YAML**: configurazioni e mappature semantiche generate.
- **Struttura di navigazione**: organizzata per categorie e capitoli, pronta per la pubblicazione.
- **Log strutturato**: registro dettagliato delle operazioni svolte e delle eventuali anomalie.

---

## 🛠 Troubleshooting

- **Errore: modulo non trovato** → Assicurati di eseguire i comandi dalla root del progetto
- **Problemi di permessi** → Verifica i permessi di scrittura sulla cartella `output/`
- **Dipendenze mancanti** → Esegui `poetry install` o `pip install -r requirements.txt`
- **Errore in onboarding\_full** → Controlla di aver completato correttamente la fase di pre-onboarding e caricato i PDF su Google Drive

---

## 📚 Risorse utili

- [Guida sviluppatore](developer_guide.md)
- [Regole di codifica](coding_rules.md)
- [Architettura tecnica](architecture.md)

