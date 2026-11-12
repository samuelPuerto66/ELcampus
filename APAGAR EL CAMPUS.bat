@echo off
rem ---------------------------------------------------------------------------
rem  Apaga El Campus del todo.
rem
rem  Lo normal es apagarlo con Ctrl+C en su propia ventana. Esto es para cuando
rem  esa ventana ya no esta (se cerro, o quedo algo prendido de antes) y al
rem  intentar prenderlo dice que el puerto 8000 o el 5173 estan ocupados.
rem
rem  Mata el proceso Y a sus hijos (/T). Sin eso, el recargador del servidor
rem  deja un hijo vivo agarrado al puerto, y el problema sigue igual.
rem ---------------------------------------------------------------------------

title Apagar El Campus
echo.
echo  Buscando El Campus...
echo.

set ENCONTRADO=0

for %%P in (8000 5173) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    echo  Apagando lo que ocupa el puerto %%P ^(proceso %%I^)...
    taskkill /PID %%I /T /F >nul 2>nul
    set ENCONTRADO=1
  )
)

rem Los hijos del recargador pueden sobrevivir al padre: se repasa una vez mas.
rem La espera va con ping y no con timeout: timeout se cae si alguien redirige
rem la entrada del script, y entonces no esperaria nada y el repaso no serviria.
call :esperar 2
for %%P in (8000 5173) do (
  for /f "tokens=5" %%I in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    echo  Quedo un proceso hijo en el puerto %%P ^(%%I^). Apagandolo...
    taskkill /PID %%I /T /F >nul 2>nul
  )
)

call :esperar 1
netstat -ano | findstr /r /c:":8000 .*LISTENING" /c:":5173 .*LISTENING" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  ---------------------------------------------------------------
  echo   Listo. El Campus esta apagado y los puertos quedaron libres.
  echo   Ya puedes volver a prenderlo con INICIAR EL CAMPUS.
  echo  ---------------------------------------------------------------
) else (
  echo.
  echo  ---------------------------------------------------------------
  echo   Quedo algo ocupando el puerto. Reinicia el PC o avisame.
  echo  ---------------------------------------------------------------
)

echo.
pause
goto :eof

rem Espera los segundos que se le pidan. ping manda un paquete por segundo a
rem este mismo PC; son N+1 intentos para esperar N segundos.
:esperar
ping -n %1 127.0.0.1 >nul 2>nul
goto :eof
