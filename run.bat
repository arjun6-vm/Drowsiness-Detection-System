@echo off
echo =======================================================
echo SafeDrive -- Application Launcher
echo =======================================================
echo.

set PYTHON_CMD=
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_CMD=.venv\Scripts\python.exe"
    echo [INFO] Using virtual environment: .venv
) else if exist "new_env\Scripts\python.exe" (
    set "PYTHON_CMD=new_env\Scripts\python.exe"
    echo [INFO] Using virtual environment: new_env
) else (
    where python >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
        echo [INFO] Using system Python interpreter.
    ) else (
        echo [ERROR] Python interpreter not found. Please run install_review.bat first.
        exit /b 1
    )
)

echo Checking MongoDB connection...
%PYTHON_CMD% -c "import pymongo, os; from dotenv import load_dotenv; load_dotenv(); uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/'); client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=2000); client.server_info()" >nul 2>nul
if %errorlevel% neq 0 (
    echo [WARNING] Could not connect to MongoDB server on port 27017.
    echo Please make sure MongoDB Community Server is started before launching SafeDrive.
    echo Example command to start MongoDB:
    echo   mongod --dbpath \"C:\data\db\"
    echo.
    set /p CONTINUE="Do you want to continue anyway? (y/n): "
    if /i not "%CONTINUE%"=="y" exit /b 1
) else (
    echo [INFO] MongoDB is active and reachable.
)

echo.
echo Starting SafeDrive at http://127.0.0.1:8000 ...
%PYTHON_CMD% app.py
