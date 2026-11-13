@echo off
rem Flutter through space-free paths (see tool\_short_paths.cmd). Use it exactly like `flutter`:
rem   tool\flutter.cmd pub get
rem   tool\flutter.cmd run -d chrome --web-port 8090 --dart-define=DEV_LOGIN=true
rem   tool\flutter.cmd test
setlocal
call "%~dp0_short_paths.cmd" || exit /b 1
call "%ZX_FLUTTER_BIN%flutter.bat" %*
exit /b %ERRORLEVEL%
