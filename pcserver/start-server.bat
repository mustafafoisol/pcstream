@echo off
REM ---------------------------------------------------------------
REM  Edit SHARE_FOLDER / TOKEN below, then double-click this file.
REM ---------------------------------------------------------------
set "SHARE_FOLDER=%USERPROFILE%\Videos"
set "PORT=8765"
set "TOKEN=changeme"

python "%~dp0serve.py" --root "%SHARE_FOLDER%" --port %PORT% --token "%TOKEN%"
if errorlevel 1 (
  echo.
  echo Server exited with an error. Is Python 3 on PATH? Try: py -3 serve.py --help
)
pause
