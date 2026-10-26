@echo off
chcp 65001 >nul
title Immo Agence
cd /d "%~dp0"

echo [1/3] Demarrage de la base de donnees...
"C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D ".pgdata" status >nul 2>&1
if errorlevel 1 (
  start "" /b "C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe" -D ".pgdata" -o "-p 5434 -c listen_addresses=localhost" -l ".pgdata\server.log" start
  timeout /t 4 /nobreak >nul
)

echo [2/3] Demarrage de l'API...
start "Immo Agence - API (ne pas fermer)" /min cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --port 8000 --env-file backend\.env"

echo [3/3] Demarrage du site...
start "Immo Agence - Site (ne pas fermer)" /min cmd /k "npm --prefix frontend run dev"

echo Ouverture du navigateur...
timeout /t 8 /nobreak >nul
start "" "http://localhost:5173/login"

echo.
echo Pret ! Espace agence : http://localhost:5173/login
echo Site public         : http://localhost:5173
echo Laissez les deux fenetres "ne pas fermer" ouvertes pendant l'utilisation.
timeout /t 10 >nul
