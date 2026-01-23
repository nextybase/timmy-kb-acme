# Quickstart - Timmy-KB (v1.0 Beta)

Guida essenziale per partire in pochi minuti.

## Prerequisiti
- Python >= 3.11
- Streamlit >= 1.50.0 (UI)
- (Opz.) Docker per anteprima HonKit
- (Opz.) Drive: `SERVICE_ACCOUNT_FILE` + `DRIVE_ID` + `pip install .[drive]`

## Avvio UI in 3 comandi
1. `streamlit run onboarding_ui.py`
2. Inserisci **slug** e **nome cliente**.
3. Completa i tab **Drive** e **Semantica** (Converti → Arricchisci → README/SUMMARY).

## Avvio CLI in 3 comandi
1. `python -m timmy_kb.cli.pre_onboarding --slug <slug> --name "<Cliente>"`
2. `python -m timmy_kb.cli.tag_onboarding --slug <slug> --proceed`
3. `python -m timmy_kb.cli.semantic_onboarding --slug <slug>`

> ⚠️ Nota Beta  
> In Beta, Timmy-KB e' strict by default.  
> L'esecuzione end-to-end e' consentita solo in Dummy Mode.  
> Vedi: [Strict vs Dummy - Guida Operativa](../strict_vs_dummy_beta.md).

## Cosa aspettarsi (Beta)
- Pipeline deterministica e tracciabile; stop espliciti, niente fallback silenziosi.
- Alcuni test UI headless sono disabilitati per policy Beta 1.0.
- La preview Docker e' facoltativa e dipende da Docker attivo.

## Prossimi passi
Approfondisci nella [User Guide](user_guide.md).
