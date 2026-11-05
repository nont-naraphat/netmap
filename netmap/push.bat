@echo off
setlocal
REM Push netmap to GitHub from Windows (cmd). Double-click or run: push.bat
REM Optional args:  push.bat "<repo-url>" <branch> "<commit message>"

set "REPO=%~1"
if "%REPO%"=="" set "REPO=https://github.com/nont-naraphat/netmap.git"
set "BRANCH=%~2"
if "%BRANCH%"=="" set "BRANCH=main"
set "MSG=%~3"
if "%MSG%"=="" set "MSG=update netmap"

where git >nul 2>&1
if errorlevel 1 (
  echo [ERROR] git not found. Install Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)

if not exist ".git" (
  git init
  git branch -M %BRANCH%
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin "%REPO%"
) else (
  git remote set-url origin "%REPO%"
)

git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "%MSG%"
) else (
  echo nothing to commit
)

git push -u origin %BRANCH%
echo.
echo done -^> %REPO% (%BRANCH%)
pause
endlocal
