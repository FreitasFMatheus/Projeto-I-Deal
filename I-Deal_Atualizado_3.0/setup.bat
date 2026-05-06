@echo off
REM ============================================================================
REM setup.bat - Setup automatico do ambiente de desenvolvimento (Windows / CMD)
REM ============================================================================
REM Uso: dentro da pasta I-Deal_Atualizado_3.0, dar duplo-clique ou rodar:
REM   setup.bat
REM ============================================================================

setlocal

echo ==============================================
echo  I-Deal - Setup do ambiente de desenvolvimento
echo ==============================================
echo.

REM 1. Verifica Python
echo [1/5] Verificando Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo       ERRO: Python nao encontrado no PATH.
    echo       Instale em: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo.

REM 2. Cria virtual env
echo [2/5] Criando ambiente virtual em .\venv ...
if exist venv (
    echo       venv ja existe - pulando criacao.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo       ERRO ao criar venv.
        pause
        exit /b 1
    )
    echo       OK: venv criado.
)
echo.

REM 3. Ativa venv
echo [3/5] Ativando o ambiente virtual...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo       ERRO ao ativar venv.
    pause
    exit /b 1
)
echo       OK: venv ativo.
echo.

REM 4. Instala dependencias
echo [4/5] Instalando dependencias (requirements.txt)...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo       ERRO ao instalar dependencias.
    pause
    exit /b 1
)
echo       OK: dependencias instaladas.
echo.

REM 5. Cria .env a partir do .env.example
echo [5/5] Configurando arquivo .env...
if not exist .env (
    if exist .env.example (
        copy .env.example .env >nul
        echo       OK: .env criado a partir do .env.example.
        echo       Edite .env e preencha ITAD_API_KEY se for usar dados reais.
    ) else (
        echo       AVISO: .env.example nao encontrado.
    )
) else (
    echo       .env ja existe - preservado.
)
echo.

echo ==============================================
echo  Setup concluido!
echo ==============================================
echo.
echo Para rodar o app:
echo   1) No VS Code, abra um terminal e ative: venv\Scripts\activate.bat
echo   2) Execute: python app.py
echo.
echo Ou aperte F5 (debug) - usa 'Python: Flask (app.py)'.
echo.
echo Acesse: http://127.0.0.1:5000
echo.
pause
