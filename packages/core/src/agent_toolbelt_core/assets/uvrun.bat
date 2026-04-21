@echo off
setlocal

:: Deprecated compatibility shim for uvrun.ps1
:: Prefer: powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uvrun.ps1" <script.py> [args...]

if "%~1"=="" (
    echo Usage: uvrun ^<script.py^> [args...]
    echo.
    echo Deprecated: uvrun.bat is a compatibility shim. Prefer uvrun.ps1.
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uvrun.ps1" %*
exit /b %ERRORLEVEL%
