# Relance tout le projet, de l'étape 2 à l'étape 5, puis ouvre l'application et la note.
# Lancement (depuis PowerShell) :  .\lancer_tout.ps1
# Si PowerShell refuse d'exécuter le script :  powershell -ExecutionPolicy Bypass -File .\lancer_tout.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

# Python qui a pandas : celui de l'installation 3.12, sinon le « python » par défaut
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
& $py -c "import pandas, openpyxl, scipy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Ce Python n'a pas pandas, openpyxl ou scipy. Installez-les : $py -m pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

$etapes = @(
    "etape01_inventaire_sources",
    "etape02_nettoyage_dgess",
    "etape02b_extraction_annuaires",
    "etape02c_projections_population",
    "etape03_transformation",
    "etape03b_fond_de_carte",
    "etape02d_extraction_esu",
    "etape03c_ecoles_accessibilite",
    "etape04_besoins_allocation",
    "etape04b_redeploiement_robustesse_decoupage",
    "etape05_application",
    "etape05b_note_decideur"
)

$debut = Get-Date
foreach ($e in $etapes) {
    Write-Host "`n=== $e ===" -ForegroundColor Cyan
    & $py "src\$e.py" | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Échec à l'étape $e : relancez-la seule pour voir l'erreur complète :  & `"$py`" src\$e.py" -ForegroundColor Red
        exit 1
    }
}
Write-Host ("`nTout est à jour ({0:N0} s)." -f ((Get-Date) - $debut).TotalSeconds) -ForegroundColor Green

$app = Get-ChildItem "data\05_interpretation\*application-aide-decision*.html" | Sort-Object LastWriteTime | Select-Object -Last 1
$note = Get-ChildItem "data\05_interpretation\*note-decideur*.pdf" | Sort-Object LastWriteTime | Select-Object -Last 1
if ($app) { Start-Process $app.FullName }
if ($note) { Start-Process $note.FullName }
