# ADR-0003: Playwright per i test end-to-end UI
- Stato: Accepted
- Data: 2025-10-30
- Responsabili: Team Timmy-KB

## Contesto
La UI Streamlit di onboarding gestisce flussi critici (creazione cliente, abilitazione servizi, anteprima docker). I test unitari/integrati coprono la logica interna ma non verificano la catena completa di interazioni utente: navigation gating, form submission, aggiornamento dei file di stato (`clients_db`, log preview). Era necessario uno strumento ripetibile che simulasse il browser senza dipendenze infrastrutturali pesanti.

## Decisione
Adottiamo **Playwright (Chromium headless)** per esercitare i percorsi UI critici in modalità end-to-end. I test girano in CI e locale con un runner dedicato (`pytest -m "e2e"`), usando Streamlit in modalità headless e gli stub applicativi (`PREVIEW_MODE=stub`, percorsi isolati tramite fixture `tmp_path`). Le dipendenze `playwright` e `pytest-playwright` sono aggiunte a `requirements-dev.in` per garantire installazioni riproducibili.

## Alternative considerate
- **Selenium / webdriver classici**: maggiore complessità di setup, necessità di driver specifici per OS, lentezza nei run deterministici.
- **Test Streamlit nativi (scripted API)**: coprono il layout ma non la reale interazione browser (click, navigation), risultando insufficienti per il contratto UX richiesto.
- **No e2e (solo integrazione)**: rischio di regressioni non individuate su gating, pulsanti e percorsi multi-step.

## Revisione
- Rivalutare se l'esecuzione Playwright in CI diventa instabile o troppo lenta (>5 min); in tal caso considerare slicing dei test o snapshot differenziati.
- Riesaminare se in futuro servirà coprire browser multipli (Firefox/WebKit) o se l'introduzione di componenti React richiederà tool aggiuntivi.
