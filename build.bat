@echo off
rem Builds dist\ValScope.exe from src\gui_web.py (needs: pip install -r requirements.txt pyinstaller)
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name ValScope ^
  --add-data "%~dp0src\web;web" ^
  --distpath dist --workpath build --specpath build ^
  src\gui_web.py
echo.
echo Done: dist\ValScope.exe  (settings.json is created next to it on first launch)
