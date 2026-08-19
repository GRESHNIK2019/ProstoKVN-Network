@echo off
setlocal
cd /d "%~dp0\.."

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% scripts\check_source.py
if errorlevel 1 (
  echo Source check failed.
  pause
  exit /b 1
)

%PY% -m pip install --user -r requirements.txt pyinstaller
if errorlevel 1 (
  echo Failed to install build dependencies.
  pause
  exit /b 1
)

%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name ProstoKVNNetwork ^
  --icon "src\assets\ProstoKVNNetwork.ico" ^
  --version-file "src\version_info.txt" ^
  --paths "src" ^
  "src\ProstoKVNNetwork.pyw"

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo EXE created: dist\ProstoKVNNetwork.exe
pause
