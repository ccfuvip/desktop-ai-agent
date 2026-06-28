# Build and Package

Two packaging paths: a Windows installer (`.exe` SETUP) using PyInstaller + Inno Setup, and a macOS disk image (`.dmg`) using BeeWare Briefcase. Both wrap the same source tree. The packaged artifact ships the Python runtime plus the eight engine modules; users still need a local llama.cpp install and GGUF models.

## Windows: SETUP.exe

### 1. Prereqs on the build machine

- Windows 10 or 11, Python 3.11 (3.12 also fine)
- Visual Studio Build Tools (for `pywin32`, `uiautomation`)
- Inno Setup 6 from https://jrsoftware.org/isdl.php
- Optional but recommended: signtool from the Windows SDK

### 2. Build the executable

```powershell
cd desktop-ai-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pyinstaller pyyaml

pyinstaller --noconfirm --clean --windowed `
  --name "DesktopAIAgent" `
  --add-data "config.yaml;." `
  --add-data "evolution_bus.py;." `
  --hidden-import "PyQt6.QtWidgets" `
  --hidden-import "PyQt6.QtCore" `
  --hidden-import "PyQt6.QtGui" `
  --collect-submodules "chromadb" `
  --collect-submodules "faster_whisper" `
  main.py
```

This produces `dist\DesktopAIAgent\DesktopAIAgent.exe` plus a folder of Python + native DLLs. First-launch size is roughly 700 MB because of ChromaDB and PyQt6; that is expected.

### 3. Wrap into a SETUP.exe with Inno Setup

Save the following as `installer.iss` next to the repo root:

```iss
[Setup]
AppName=Desktop AI Agent
AppVersion=1.0.0
AppPublisher=ccfuvip
DefaultDirName={autopf}\DesktopAIAgent
DefaultGroupName=Desktop AI Agent
OutputBaseFilename=DesktopAIAgent-Setup-1.0.0
Compression=lzma2/ultra
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\DesktopAIAgent\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Desktop AI Agent"; Filename: "{app}\DesktopAIAgent.exe"
Name: "{group}\Start llama.cpp servers"; Filename: "{app}\python.exe"; Parameters: """{app}\start_servers.py"""
Name: "{commondesktop}\Desktop AI Agent"; Filename: "{app}\DesktopAIAgent.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts"
```

Build it:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The result is `Output\DesktopAIAgent-Setup-1.0.0.exe`. Distribute that file. Double-clicking installs into `C:\Program Files\DesktopAIAgent` and creates the Start Menu + desktop shortcuts.

### 4. Code signing (recommended before sharing)

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f path\to\codesign.pfx /p $env:CODESIGN_PWD `
  dist\DesktopAIAgent\DesktopAIAgent.exe
```

Without signing Windows SmartScreen will warn on first run; the warning clears after enough users click through. For personal use, you can skip signing and document the SmartScreen step in the README.

## macOS: DMG

### 1. Prereqs on the build machine

- macOS 12+, Xcode command line tools
- Python 3.11 (`brew install python@3.11`)
- A Developer ID Application certificate in your keychain (for notarization)

### 2. Build with Briefcase

Briefcase produces a `.app` bundle plus a `.dmg`. It expects a `pyproject.toml` so the project must declare itself as a Briefcase project. A minimal `pyproject.toml` at the repo root:

```toml
[project]
name = "desktop-ai-agent"
version = "1.0.0"
description = "Self-evolving multimodal desktop agent"
authors = [{name = "ccfuvip"}]
requires-python = ">=3.11"

[tool.briefcase]
project_name = "DesktopAIAgent"
bundle = "com.ccfuvip.desktopaiagent"
version = "1.0.0"
url = "https://github.com/ccfuvip/desktop-ai-agent"
license = "Proprietary"
author = "ccfuvip"
author_email = "noreply@example.com"

[tool.briefcase.app.desktop-ai-agent]
formal_name = "Desktop AI Agent"
description = "Self-evolving multimodal desktop agent"
icon = "icons/app"
sources = ["main.py", "agent_core.py", "awareness_engine.py", "controller_engine.py", "multimodal_engine.py", "memory_store.py", "learning_engine.py", "upgrade_engine.py", "optimization_engine.py", "collaboration_engine.py", "evolution_bus.py", "remote_control.py", "ui_main.py"]
requires = [
    "PyQt6>=6.7.0",
    "mss>=10.0.0",
    "uiautomation>=2.0.15",
    "pyautogui>=0.9.54",
    "keyboard>=0.13.5",
    "pyobjc-framework-Cocoa>=10.0",
    "playwright>=1.48.0",
    "chromadb>=0.6.0",
    "httpx>=0.28.0",
    "faster-whisper>=1.1.0",
    "duckduckgo-search>=6.0.0",
    "requests>=2.31.0",
    "feedparser>=6.0.0",
    "beautifulsoup4>=4.12.0",
    "networkx>=3.2.0",
    "pyyaml>=6.0.0",
]

[tool.briefcase.app.desktop-ai-agent.macOS]
universal_build = true
requires = []
```

Then:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install briefcase
briefcase create macOS
briefcase build macOS
briefcase package macOS --no-sign
```

`briefcase package` produces `macOS\app\Desktop AI Agent-1.0.0.dmg`. Double-click to mount, drag into Applications.

### 3. Notarize

Without notarization Gatekeeper blocks the app on first launch. To notarize:

```bash
xcrun notarytool submit "macOS/app/Desktop AI Agent-1.0.0.dmg" `
  --apple-id $APPLE_ID --team-id $APPLE_TEAM_ID `
  --password $APPLE_APP_PASSWORD --wait
xcrun stapler staple "macOS/app/Desktop AI Agent-1.0.0.dmg"
```

Re-package with signing once the certificate is wired in:

```bash
briefcase package macOS
```

## Verifying a packaged build

After installing the SETUP.exe or dragging the .app to /Applications, the install includes a smoke test entry point that does not require llama.cpp servers:

- Windows: `C:\Program Files\DesktopAIAgent\python.exe -m smoke_test` (the spec adds a console script wrapper).
- macOS: `Desktop AI Agent.app/Contents/Resources/Support/Python.framework/Versions/Current/bin/python -m smoke_test`.

If the package is built correctly, you should see `SMOKE TEST PASSED` within one second.

## Size and disk footprint

| Component                | Approx. size |
|--------------------------|--------------|
| Windows installer EXE    | ~ 280 MB compressed, ~ 700 MB unpacked |
| macOS DMG                | ~ 240 MB compressed, ~ 600 MB unpacked |
| llama.cpp + GGUF models  | ~ 9 GB (Hermes 3 8B + Qwen 2.5 VL 7B) |

The agents and model files are intentionally separate. The installer ships only the orchestration code; users point `config.yaml` at their own model paths.

## CI

A GitHub Actions workflow under `.github/workflows/build.yml` runs the smoke test on every push and builds the Windows installer on tagged releases. The macOS build runs only on Apple runners for tagged releases.

## Local development vs packaged build

During development, run from source via `python main.py`. PyInstaller-frozen builds rebuild `sys.path`, so relative imports inside the engine modules still work as long as `main.py` is the entry point and PyInstaller bundles every `.py` listed in `--add-data` or `sources` above. The `_smoke_test.py` is the canary: if it stops passing after a packaging change, suspect the `--hidden-import` or `--collect-submodules` flags first.