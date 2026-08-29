@echo off
chcp 65001 >nul
setlocal
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONIOENCODING=utf-8"
set "TOOLDIR=%~dp0"
set "PYEXE=%TOOLDIR%.venv\Scripts\python.exe"

if not exist "%PYEXE%" (
  echo [setup] First run: creating local Python env, please wait...
  py -3 -m venv "%TOOLDIR%.venv"
  if errorlevel 1 (
    echo [setup] "py -3" failed, trying "python"...
    python -m venv "%TOOLDIR%.venv"
  )
  if not exist "%TOOLDIR%.venv\Scripts\python.exe" (
    echo ERROR: Python 3 not found. Install it from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  "%TOOLDIR%.venv\Scripts\python.exe" -m pip install -q lxml
  if errorlevel 1 (
    echo ERROR: failed to install lxml. Check your network connection.
    pause
    exit /b 1
  )
)

if "%~1"=="" (
  echo.
  echo   Drag one or more .epub files onto this .bat
  echo   Output: same folder, filename + "-tight.epub"
  echo   Mode:   tight - smallest spacing, no rule line, indent only
  echo.
  pause
  exit /b 0
)

:loop
if "%~1"=="" goto done
"%PYEXE%" "%TOOLDIR%epub_footnote_inline.py" "%~1" --suffix=-tight --style tight --class-fallback
if errorlevel 1 echo   [FAILED] %~nx1
shift
goto loop

:done
echo.
echo All done.
pause
