[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$backendDir = $PSScriptRoot
$python = Join-Path $backendDir '.venv\Scripts\python.exe'

function Stop-WithHelp([string] $Message) {
    Write-Error "$Message`nConsultez README.md, section « Démarrage après redémarrage du PC »."
    exit 1
}

try {
    $qdrant = Invoke-RestMethod -Uri 'http://127.0.0.1:6333/collections' -TimeoutSec 4
} catch {
    Stop-WithHelp 'Qdrant ne répond pas sur 127.0.0.1:6333. Démarrez Docker Desktop puis exécutez `docker compose up -d qdrant` depuis la racine du projet.'
}
$collectionNames = @($qdrant.result.collections | ForEach-Object { $_.name })
$expectedCollections = @('emsi_text', 'emsi_images')
$missingCollections = @($expectedCollections | Where-Object { $_ -notin $collectionNames })
if ($missingCollections.Count -gt 0) {
    Stop-WithHelp "Collection(s) Qdrant absente(s) : $($missingCollections -join ', '). Le script ne lance aucune indexation."
}

try {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 2 | Out-Null
    Write-Host 'FastAPI répond déjà sur http://127.0.0.1:8000/health.'
    exit 0
} catch {
    # Aucun backend ne répond ; poursuivre le démarrage.
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    Stop-WithHelp "Interpréteur introuvable : $python. Créez l'environnement avec Python 3.11 avant de démarrer l'API."
}

$venvConfig = Join-Path $backendDir '.venv\pyvenv.cfg'
if (Test-Path -LiteralPath $venvConfig -PathType Leaf) {
    $runtimeLine = Select-String -LiteralPath $venvConfig -Pattern '^executable\s*=\s*(.+)$' | Select-Object -First 1
    if ($runtimeLine) {
        $basePython = $runtimeLine.Matches[0].Groups[1].Value.Trim()
        if (-not (Test-Path -LiteralPath $basePython -PathType Leaf)) {
            Stop-WithHelp "Le runtime Python de base du venv est introuvable : $basePython. Réparez Python 3.11 avant de démarrer FastAPI."
        }
    }
}

Push-Location $backendDir
try {
    & $python --version
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp 'L''interpréteur du venv ne démarre pas correctement. Vérifiez backend/.venv/pyvenv.cfg et le runtime Python de base.'
    }
    & $python -m uvicorn --version
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp 'Uvicorn est absent de backend/.venv. Installez backend/requirements.txt dans cet environnement.'
    }
    Write-Host 'Démarrage de FastAPI sur 0.0.0.0:8000. Gardez cette fenêtre ouverte.'
    & $python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
    if ($LASTEXITCODE -ne 0) {
        Stop-WithHelp ('Code de sortie Uvicorn : ' + $LASTEXITCODE)
    }
} finally {
    Pop-Location
}




