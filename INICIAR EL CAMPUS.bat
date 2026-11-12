@echo off
rem ---------------------------------------------------------------------------
rem  Prende El Campus con doble clic, sin tener que abrir una terminal ni
rem  acordarse de en que carpeta va el comando.
rem
rem  Lo unico que hace es pararse en la carpeta correcta y llamar a "npm start",
rem  que es quien hace el trabajo de verdad (ver ELcampus\iniciar.mjs).
rem
rem  Para apagarlo: Ctrl+C en esta ventana, o simplemente cerrarla.
rem ---------------------------------------------------------------------------

title El Campus

rem %~dp0 es la carpeta donde esta este archivo, sin importar desde donde se
rem abra. Asi funciona igual en el escritorio, dentro de Campus o en una USB.
cd /d "%~dp0"

rem El proyecto puede estar aqui mismo o un nivel adentro, en ELcampus.
if exist "ELcampus\package.json" cd "ELcampus"

if not exist "package.json" (
  echo.
  echo  No encontre el proyecto El Campus desde esta carpeta:
  echo    %CD%
  echo.
  echo  Mueve este archivo junto a la carpeta ELcampus y vuelve a intentar.
  echo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo  No esta instalado Node.js, que es lo que necesita El Campus para
  echo  prender. Instalalo desde https://nodejs.org (la version LTS^) y
  echo  vuelve a darle doble clic a este archivo.
  echo.
  pause
  exit /b 1
)

call npm start

rem Si algo fallo, la ventana se queda abierta para poder leer el error.
rem Con Ctrl+C tambien pasa por aqui, y asi se ve que ya quedo apagado.
echo.
echo  ---------------------------------------------------------------
echo   El Campus se apago. Ya puedes cerrar esta ventana.
echo  ---------------------------------------------------------------
echo.
pause
