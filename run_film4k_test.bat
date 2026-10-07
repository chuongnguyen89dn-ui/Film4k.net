@echo off
setlocal
cd /d "%~dp0"
python -m pip install -q requests
python film4k_test.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] Film4K test failed.
  exit /b %errorlevel%
)
echo.
echo [PASS] Film4K test completed.
