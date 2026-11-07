@echo off
echo =======================================================
echo SafeDrive -- Dependency Installation Script
echo ======================================================
echo.

set PYTHON_CMD=
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    echo [INFO] Found existing virtual environment: .venv
) else if exist "new_env\Scripts\python.exe" (
    set "PYTHON_CMD=new_env\Scripts\python.exe"
    echo [INFO] Found existing virtual environment: new_env
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
        echo [INFO] Using system Python interpreter.
    ) else (
        echo [ERROR] No Python interpreter found in PATG or virtual environments.
        echo Please install Python 3.10 or 3.11 and add it to your PATH.
        exit /b 1
    )
)

echo Checking Python version...
%PYTHON_CMD% -c "import sys; v = sys.version_info; sys.exit(0 if (v.major == 3 and v.minor in [10, 11]) else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Unsupported Python version detected.
    echo SafeDrive requires Python 3.10 or 3.11 for MediaPipe compatibility on Windows.
    echo Current Python interpreter: %PYTHON_CMD%
    echo Please install Python 3.10 or 3.11 from https://www.python.org/downloads/
    exit /b 1
)

echo.
echo Installing packages from requirements.txt...
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Package installation failed. Please review pip error details above.
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [INFO] Created .env template from .env.example. Please update your credentials.
    )
) else (
    echo [INFO] Existing .env file preserved.
)

echo.
echo =======================================================
echo [SUCCESS] Dependencies installed successfully.
echo ======================================================
