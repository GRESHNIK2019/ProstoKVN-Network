@echo off
setlocal
cd /d "%~dp0\.."
title Smart VPN Launcher

where py >nul 2>&1
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)

%PY% -c "import yaml" >nul 2>&1
if errorlevel 1 (
  echo Installing required Python package PyYAML...
  %PY% -m pip install --user PyYAML
  if errorlevel 1 (
    echo Failed to install PyYAML.
    pause
    exit /b 1
  )
)

for /f "delims=" %%I in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%I"
if defined PYW (
  start "" "%PYW%" "%CD%\src\SmartVPN.pyw"
) else (
  %PY% "%CD%\src\SmartVPN.pyw"
)
exit /b 0
