@echo off
rem ===================================================================
rem  Immo Agence - installation (a lancer UNE seule fois)
rem  Installe la base de donnees comme service Windows "ImmoAgenceDB" :
rem  elle demarre automatiquement avec le PC et reste toujours prete.
rem  Windows demande l'autorisation administrateur : repondre Oui.
rem  Les donnees actuelles sont COPIEES (l'original reste dans .pgdata).
rem ===================================================================
chcp 65001 >nul

net session >nul 2>&1
if errorlevel 1 (
  echo Demande des droits administrateur...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

set "ROOT=%~dp0.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "PGBIN=C:\Program Files\PostgreSQL\18\bin"
set "SRC=%ROOT%\.pgdata"
set "DATA=%ProgramData%\ImmoAgence\pgdata"
set "SVC=ImmoAgenceDB"

echo.
echo Application : %ROOT%
echo Donnees     : %DATA%
echo.

sc query %SVC% >nul 2>&1
if not errorlevel 1 (
  echo Le service %SVC% existe deja : redemarrage.
  sc stop %SVC% >nul 2>&1
  timeout /t 4 /nobreak >nul
  sc start %SVC% >nul
  goto :check
)

echo [1/4] Arret de la base de developpement...
"%PGBIN%\pg_ctl.exe" -D "%SRC%" stop -m fast >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/4] Copie des donnees vers %DATA% ...
if exist "%DATA%\PG_VERSION" (
  echo      Des donnees existent deja a cet endroit : elles sont conservees.
) else (
  robocopy "%SRC%" "%DATA%" /E /XF postmaster.pid postmaster.opts server.log /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 goto :fail
)
icacls "%ProgramData%\ImmoAgence" /grant "NT AUTHORITY\NetworkService:(OI)(CI)M" /T /Q >nul

echo [3/4] Installation du service %SVC% (demarrage automatique)...
"%PGBIN%\pg_ctl.exe" register -N %SVC% -D "%DATA%" -S auto -o "-p 5434 -c listen_addresses=localhost -c logging_collector=on -c log_directory=log"
if errorlevel 1 goto :fail

echo [4/4] Demarrage du service...
sc start %SVC% >nul

:check
timeout /t 6 /nobreak >nul
sc query %SVC% | find "RUNNING" >nul
if errorlevel 1 goto :fail

echo.
echo  ==^> Installation terminee. Ouvrez "Immo Agence" depuis le Bureau.
echo.
pause
exit /b 0

:fail
echo.
echo  ==^> L'installation a echoue. Envoyez une capture de cette fenetre.
echo.
pause
exit /b 1
