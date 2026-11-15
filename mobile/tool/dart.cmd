@echo off
rem Dart through space-free paths (see tool\_short_paths.cmd). Use it exactly like `dart`:
rem   tool\dart.cmd run build_runner build --delete-conflicting-outputs
rem   tool\dart.cmd format lib test
setlocal
call "%~dp0_short_paths.cmd" || exit /b 1
call "%ZX_FLUTTER_BIN%dart.bat" %*
exit /b %ERRORLEVEL%
