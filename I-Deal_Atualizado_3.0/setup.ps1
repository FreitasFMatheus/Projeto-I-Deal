$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== I-Deal: Setup do ambiente ===" -ForegroundColor Cyan
Write-Host ""

# 1. Verifica Python
Write-Host "[1/5] Verificando Python..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "      OK: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "      ERRO: Python nao encontrado." -ForegroundColor Red
    Write-Host "      Baixe em: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# 2. Cria venv
Write-Host ""
Write-Host "[2/5] Criando ambiente virtual (venv)..." -ForegroundColor Yellow
if (Test-Path ".\venv") {
    Write-Host "      venv ja existe, pulando." -ForegroundColor DarkGray
} else {
    python -m venv venv
    Write-Host "      OK: venv criado." -ForegroundColor Green
}

# 3. Ativa venv
Write-Host ""
Write-Host "[3/5] Ativando o venv..." -ForegroundColor Yellow
. ".\venv\Scripts\Activate.ps1"
Write-Host "      OK: venv ativo." -ForegroundColor Green

# 4. Instala dependencias
Write-Host ""
Write-Host "[4/5] Instalando dependencias..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Write-Host "      OK: dependencias instaladas." -ForegroundColor Green

# 5. Cria .env
Write-Host ""
Write-Host "[5/5] Configurando .env..." -ForegroundColor Yellow
if (-not (Test-Path ".\.env")) {
    if (Test-Path ".\.env.example") {
        Copy-Item ".\.env.example" ".\.env"
        Write-Host "      OK: .env criado." -ForegroundColor Green
    }
} else {
    Write-Host "      .env ja existe, preservado." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Setup concluido! ===" -ForegroundColor Green
Write-Host ""
Write-Host "Para rodar o app, digite:" -ForegroundColor White
Write-Host "  python app.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "Depois acesse: http://127.0.0.1:5000" -ForegroundColor Cyan
Write-Host ""
