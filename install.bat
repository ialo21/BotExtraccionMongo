@echo off
setlocal

REM Crea/reutiliza .venv, instala deps y navegador. Simplificado para evitar errores de parentesis.

set "VENV_DIR=.venv"
set "PYTHON=%VENV_DIR%\Scripts\python.exe"

if exist "%PYTHON%" (
    echo [INFO] Reutilizando entorno virtual %VENV_DIR%
) else (
    echo [INFO] Creando entorno virtual (intenta py -3.11, si no usa py por defecto)...
    py -3.11 -m venv %VENV_DIR% >nul 2>&1
    if errorlevel 1 (
        echo [WARN] No se encontro py -3.11, probando con py por defecto
        py -m venv %VENV_DIR% >nul 2>&1
    )
)

if not exist "%PYTHON%" (
    echo [ERROR] No se pudo crear %VENV_DIR%. Verifica que Python esta instalado y accesible.
    exit /b 1
)

echo [INFO] Actualizando pip...
"%PYTHON%" -m pip install --upgrade pip || goto :fail

echo [INFO] Instalando dependencias de requirements.txt...
"%PYTHON%" -m pip install -r requirements.txt || goto :fail

echo [INFO] Instalando navegador Playwright (chromium)...
"%PYTHON%" -m playwright install chromium || goto :fail

echo [OK] Listo. Para activar el entorno: call %VENV_DIR%\Scripts\activate
exit /b 0

:fail
echo [ERROR] Ocurrio un error durante la instalacion. Revisa el mensaje anterior.
exit /b 1
endlocal
