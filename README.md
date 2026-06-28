# Desktop AI Agent

Self-evolving multimodal desktop agent. Eight cooperating engines share an event bus, drive a ReAct loop, and run entirely on local llama.cpp inference. No cloud calls.

- Text: Hermes-3-Llama-3.1-8B (Q6_K)
- Vision: Qwen2.5-VL-7B (Q6_K)
- Inference: llama.cpp HTTP API on `127.0.0.1:8080` / `:8081`
- GPU: NVIDIA RTX 5080 (16 GB), CUDA 13.3

## Quick Start (Windows)

```powershell
git clone https://github.com/ccfuvip/desktop-ai-agent.git
cd desktop-ai-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pyyaml

# 1. Start llama.cpp servers (text on 8080, vision on 8081)
python start_servers.py

# 2. Launch the agent
python main.py

# Or jump straight into a one-shot task
python main.py -m "open Notepad and type hello"

# Or open the PyQt6 desktop UI
python main.py --gui
```

The first run builds `data/` (memory, logs, skills, knowledge). Subsequent runs reuse it.

## Quick Start (macOS / Linux)

Same steps, with two changes:

```bash
git clone https://github.com/ccfuvip/desktop-ai-agent.git
cd desktop-ai-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pyyaml

python start_servers.py   # needs the macOS / Linux llama.cpp build
python main.py
```

`start_servers.py` is platform-aware: it locates `llama-server` on PATH or under `~/AI_Models/` and falls back to plain-text mode if the vision model is not configured.

## Architecture

```
                    +-------------------------------+
                    |  PyQt6 UI + Evolution Dashboard |
                    +---------------+---------------+
                                    |
                    +---------------v---------------+
                    |     AgentCore (ReAct loop)    |
                    |  SafetyGuard | SelfChecker    |
                    +--+-----+-----+-----+-----+----+
                       |     |     |     |     |
   +-------------------+     |     |     |     +--------------------+
   |                         |     |     |                          |
+-v----------+   +-----------v-+ +-v---+ +-v----------+   +---------v-------+
| Awareness  |   | Controller  | | Memory| | Multimodal |   | Evolution Bus  |
| (UIA / mss)|   | (pyautogui) | |(Chroma)| | (llama.cpp)|   |  (pub/sub)    |
+-----+------+   +-------+-----+ +--+----+ +-----+------+   +--+-----+------+
      |                  |          |            |               |     |     |
      +------------------+----------+------------+        +-----v-+ +-v---+ +v-----+
                                                            |Learning| |Upgrade| |Optim.|  |Collab|
                                                            +--------+ +-------+ +------+ +------+
```

All four evolution engines subscribe to the bus via `set_event_bus()`. Every emit is appended to `data/logs/evolution_events.jsonl` and surfaces in the dashboard.

## Engines

| Engine              | File                       | Role                                                           |
|---------------------|----------------------------|----------------------------------------------------------------|
| AgentCore           | `agent_core.py`            | ReAct orchestrator, safety guard, self-checker, reflection     |
| DesktopAwareness    | `awareness_engine.py`      | Screen capture, window enumeration, mouse position             |
| DesktopAutomation   | `controller_engine.py`     | Click / type / hotkey / window ops via pyautogui + pywin32     |
| Multimodal          | `multimodal_engine.py`     | llama.cpp HTTP client (text + vision)                          |
| Memory              | `memory_store.py`          | ChromaDB long-term, short-term ring, experience log            |
| Learning            | `learning_engine.py`       | Knowledge acquisition (DDG / Bing / GitHub / HN / arXiv)        |
| Upgrade             | `upgrade_engine.py`        | Model / dependency upgrade checks, sandbox test, backup         |
| Optimization        | `optimization_engine.py`   | Performance monitoring, strategy reflection, resource scheduling |
| Collaboration (MCP) | `collaboration_engine.py`  | Multi-agent dispatch via Model Context Protocol registry       |

The event bus lives in `evolution_bus.py`. It is the single integration point for any new engine: call `set_event_bus(bus)`, then `bus.emit("your_source", "your_event_kind", payload)`.

## Configuration

`config.yaml` controls ports, model paths, CUDA layer counts, capture FPS, and the four evolution subsystems. Override `llama_cpp.text_model.path` and `vision_model.path` to point at your GGUF files. The defaults assume the layout the project ships with on the developer's RTX 5080.

## CLI

```
python main.py                    # REPL: type a task, get an answer
python main.py -m "task"          # one-shot, exits after the task
python main.py --gui              # PyQt6 window
python main.py --headless         # skip live LLM health check (useful for CI / smoke tests)

# Inside the REPL:
:stats    # show EvolutionBus snapshot + AgentCore status
:health   # show llama.cpp server health
:recent   # show last 10 bus events
:help     # list commands
:quit     # exit
```

## Smoke Test

Verifies the wiring without needing the llama.cpp servers:

```
python _smoke_test.py
```

Expected last lines:

```
[6/7] execute_task returned success=True, steps=1, duration=0.22s
[7/7] EvolutionBus snapshot captured events from: agent_core, collaboration, learning, optimization, upgrade

SMOKE TEST PASSED
```

## Directory Layout

```
desktop-ai-agent/
├── main.py                       # CLI + GUI entry point
├── config.yaml                   # runtime config
├── requirements.txt
├── agent_core.py                 # AgentCore, SafetyGuard, SelfChecker
├── awareness_engine.py
├── controller_engine.py
├── multimodal_engine.py
├── memory_store.py
├── learning_engine.py
├── upgrade_engine.py
├── optimization_engine.py
├── collaboration_engine.py
├── evolution_bus.py              # pub/sub bus, JSONL log
├── remote_control.py             # optional LAN control server
├── ui_main.py                    # PyQt6 MainWindow
├── start_servers.py              # llama.cpp launcher (replaces start_servers.bat)
├── start_agent.py                # agent launcher (replaces start_agent.bat)
├── _smoke_test.py                # headless smoke test
├── data/                         # runtime data, gitignored
│   ├── logs/evolution_events.jsonl
│   ├── memory/                   # ChromaDB
│   ├── skills/  plugins/  knowledge/
└── BUILD.md                      # Windows SETUP + macOS DMG packaging
```

## Troubleshooting

- `requests.exceptions.ConnectionError` on `127.0.0.1:8080` — `python start_servers.py` did not finish booting; check the terminal for llama.cpp stderr.
- `MultimodalEngine is_ready()` returns False — either the text model or the vision model failed to bind. Run `start_servers.py --stop` then `start_servers.py` again.
- `pip install` fails on PyQt6 — use Python 3.11 or 3.12; PyQt6 wheels are not published for 3.13 on Windows yet.
- Smoke test reports `expected learning or optimization event` — an engine regressed; rerun with `set_event_bus()` calls traced.
- ChromaDB import error — `pip install chromadb>=0.6.0`. If the install fails, set `CHROMA_DISABLE_TELEMETRY=1` and retry.

## License

Personal project. Not published under an OSI license yet.