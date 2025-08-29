# Qodana baseline (native) – PowerShell one-shot
# Lancialo dalla root del repo, sul branch della PR (es. chore/repo-hygiene)

$ErrorActionPreference = 'Stop'

function Info($m){ Write-Host "[i] $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "[!] $m" -ForegroundColor Yellow }
function Die($m){ Write-Host "[x] $m" -ForegroundColor Red ; exit 1 }

# 0) Verifiche base
& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) { Die "Non sei in un repository Git." }

# 1) qodana.yaml: crea/aggiorna in root (mantiene exclude se già presenti)
$yamlPath = Join-Path (Get-Location) "qodana.yaml"
$needsExclude = $true
if (Test-Path $yamlPath) {
  $yaml = Get-Content $yamlPath -Raw

  # forza linter + bootstrap (idempotente)
  if ($yaml -match "(?m)^\s*linter\s*:") {
    $yaml = $yaml -replace "(?m)^\s*linter\s*:.*$", "linter: qodana-python-community"
  } else {
    $yaml += "`n" + "linter: qodana-python-community"
  }
  if ($yaml -match "(?m)^\s*bootstrap\s*:") {
    $yaml = $yaml -replace "(?m)^\s*bootstrap\s*:.*$", "bootstrap: py -m pip install -r requirements.txt"
  } else {
    $yaml += "`n" + "bootstrap: py -m pip install -r requirements.txt"
  }
  if ($yaml -match "(?s)^\s*exclude\s*:") { $needsExclude = $false }

  Set-Content -Path $yamlPath -Value $yaml -Encoding UTF8
  Info "Aggiornato $yamlPath (linter/bootstrap)."
} else {
  @"
version: "1.0"
linter: qodana-python-community
bootstrap: py -m pip install -r requirements.txt
exclude:
  - name: All
    paths:
      - "output/**"
      - "logs/**"
      - ".venv/**"
      - "venv/**"
      - "__pycache__/**"
"@ | Set-Content -Path $yamlPath -Encoding UTF8
  Info "Creato $yamlPath (minimo utile)."
  $needsExclude = $false
}

if ($needsExclude) {
@"
exclude:
  - name: All
    paths:
      - "output/**"
      - "logs/**"
      - ".venv/**"
      - "venv/**"
      - "__pycache__/**"
"@ | Add-Content -Path $yamlPath -Encoding UTF8
  Info "Aggiunti exclude standard a $yamlPath."
}

# 2) Ambiente Python (venv) e dipendenze
if (Test-Path ".\.venv\Scripts\Activate.ps1") {
  & .\.venv\Scripts\Activate.ps1
} else {
  Info "Creo venv locale .venv"
  py -m venv .venv
  & .\.venv\Scripts\Activate.ps1
}
py -m pip install -U pip
if (Test-Path "requirements.txt") {
  Info "Installo dipendenze (requirements.txt)"
  py -m pip install -r requirements.txt
} else {
  Warn "requirements.txt non trovato: salto install dipendenze."
}

# 3) Qodana CLI presente?
$q = Get-Command qodana -ErrorAction SilentlyContinue
if (-not $q) {
  Warn "Qodana CLI non trovata. Provo l’install con winget (potrebbe chiedere conferma)..."
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install -e --id JetBrains.Qodana.CLI --silent
    $q = Get-Command qodana -ErrorAction SilentlyContinue
  }
  if (-not $q) { Die "Installa Qodana CLI e rilancia: winget install JetBrains.Qodana.CLI  (o: choco install qodana-cli)" }
}
Info "Qodana CLI ok."

# 4) Scansione nativa (senza Docker) e salvataggio artefatti
$qodanaOut = ".qodana/results"
New-Item -ItemType Directory -Force -Path $qodanaOut | Out-Null
Info "Eseguo: qodana scan (native)…"
qodana scan --within-docker false --linter qodana-python-community --results-dir $qodanaOut --save-report

# 5) Copia del baseline reale in root
$sarifSrc = Join-Path $qodanaOut "qodana.sarif.json"
if (-not (Test-Path $sarifSrc)) { Die "SARIF non trovato: $sarifSrc" }
Copy-Item $sarifSrc "qodana.sarif.json" -Force
Info "Baseline aggiornato: ./qodana.sarif.json"

# 6) Commit & push (solo se ci sono cambiamenti)
& git add qodana.sarif.json qodana.yaml
& git diff --cached --quiet
$hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
  & git commit -m "ci(qodana): refresh baseline (native scan)"
  if ($LASTEXITCODE -eq 0) {
    Info "Commit creato. Eseguo push…"
    & git push
  } else {
    Die "Commit fallito."
  }
} else {
  Info "Nessuna modifica da commitare (baseline invariato)."
}

# 7) Riepilogo
Write-Host ""
Write-Host "== Riepilogo ==" -ForegroundColor Green
Write-Host "• Aggiornato: qodana.yaml"
Write-Host "• Generato:  qodana.sarif.json (baseline reale)"
Write-Host "• Artefatti: $qodanaOut (locale, non necessario committarli)"
Write-Host ""
Write-Host "Ora riapri la PR e rilancia i check. Il gate (fail-threshold) bloccherà solo problemi NUOVI rispetto al baseline."
