@echo off
rem Shared by tool\flutter.cmd and tool\dart.cmd (called with CALL, so the variables reach the caller).
rem
rem Why: on Windows, when the Flutter SDK or the pub cache sits under a folder with a space
rem (e.g. C:\Users\First Last\...), Flutter compiles native-assets hooks (package:objective_c, pulled in
rem by path_provider_foundation) through cmd without quoting the SDK path and fails with
rem "'C:\Users\First' is not recognized as an internal or external command".
rem Fix: run Flutter and Dart through the 8.3 short names of the same folders (e.g. C:\Users\FIRST~1),
rem which contain no spaces. Nothing is moved or installed, and nothing outside this process changes.
rem
rem Sets: ZX_FLUTTER_BIN (short path of <sdk>\bin\, with trailing backslash), PUB_CACHE (short path).

set "ZX_FLUTTER_BAT="
if defined FLUTTER_ROOT if exist "%FLUTTER_ROOT%\bin\flutter.bat" set "ZX_FLUTTER_BAT=%FLUTTER_ROOT%\bin\flutter.bat"
if not defined ZX_FLUTTER_BAT for %%F in (flutter.bat) do set "ZX_FLUTTER_BAT=%%~$PATH:F"
if not defined ZX_FLUTTER_BAT (
  echo [tool] flutter.bat was not found on PATH. Add ^<flutter sdk^>\bin to PATH or set FLUTTER_ROOT. 1>&2
  exit /b 1
)
for %%F in ("%ZX_FLUTTER_BAT%") do set "ZX_FLUTTER_BIN=%%~dpsF"

if not defined PUB_CACHE set "PUB_CACHE=%LOCALAPPDATA%\Pub\Cache"
if not exist "%PUB_CACHE%" mkdir "%PUB_CACHE%"
for %%P in ("%PUB_CACHE%") do set "PUB_CACHE=%%~sP"

set "ZX_CHECK=%ZX_FLUTTER_BIN%%PUB_CACHE%"
if not "%ZX_CHECK: =%"=="%ZX_CHECK%" (
  echo [tool] A path still contains a space: 8.3 short names are disabled on this drive. 1>&2
  echo [tool] One-time fix: mklink /J C:\flutter ^<your flutter sdk folder^>, put C:\flutter\bin on PATH, 1>&2
  echo [tool] and set PUB_CACHE to a folder without spaces, e.g. C:\pub-cache. 1>&2
  exit /b 1
)
set "ZX_CHECK="
set "PATH=%ZX_FLUTTER_BIN%;%PATH%"
exit /b 0
