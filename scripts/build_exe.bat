@echo off
setlocal
cd /d "%~dp0\.."

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% -m pip install --user PyInstaller PyYAML
if errorlevel 1 (
  echo Failed to install build dependencies.
  pause
  exit /b 1
)

%PY% -m PyInstaller --noconfirm --clean --onefile --noconsole --name SmartVPN src\SmartVPN.pyw
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo EXE created in dist\SmartVPN.exe
pause
