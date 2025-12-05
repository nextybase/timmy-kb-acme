<#
.SYNOPSIS
    Imposta REPO_ROOT_DIR per far puntare Pipeline al repo di lavoro.

.DESCRIPTION
    Esporta la variabile `REPO_ROOT_DIR` basandosi sul percorso fornito o sulla
    directory corrente. Serve per forzare `ClientContext`/`pipeline` a risolvere
    i workspace dentro la working tree invece che dentro `venv\Lib`.
    Questo script Ã¨ idempotente e va richiamato prima di lanciare Streamlit.
#>
Param(
    [string]$Root = (Get-Location).ProviderPath
)

$rootPath = Resolve-Path -Path $Root
$canonicalRoot = $rootPath.ProviderPath
Write-Host "Imposto REPO_ROOT_DIR=$canonicalRoot"
$env:REPO_ROOT_DIR = $canonicalRoot

$currentPythonPath = $env:PYTHONPATH
if ($currentPythonPath) {
    $newPythonPath = "$canonicalRoot;$currentPythonPath"
} else {
    $newPythonPath = $canonicalRoot
}
$env:PYTHONPATH = $newPythonPath
Write-Host "Aggiorno PYTHONPATH=$newPythonPath"
