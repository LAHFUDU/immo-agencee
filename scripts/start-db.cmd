@echo off
rem Starts the project-local PostgreSQL (port 5434) if it is not already running.
cd /d "%~dp0.."
set PGCTL="C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe"
%PGCTL% -D .pgdata status >nul 2>&1
if errorlevel 1 (
  %PGCTL% -D .pgdata -o "-p 5434 -c listen_addresses=localhost" -l .pgdata\server.log -W start
  timeout /t 4 /nobreak >nul
)
echo Base de donnees prete (port 5434).
