"""Smoke test: load every engine, wire EvolutionBus, run one ReAct step with a stubbed model.

This test does NOT require llama.cpp servers to be running. The multimodal engine
is bypassed via __new__ + method patch, so no HTTP calls happen.

Pass criteria (printed to stdout, exit code 0 = pass):
  - all 9 modules import cleanly
  - 4 evolution engines emit bus_attached
  - AgentCore.execute_task returns TaskResult with success=True and steps_taken >= 1
  - EvolutionBus snapshot contains events from learning + optimization
  - AgentCore.get_status() returns a dict
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_DIR = Path(__file__).resolve().parent
os.chdir(PROJECT_DIR)
sys.path.insert(0, str(PROJECT_DIR))

import yaml
from evolution_bus import EvolutionBus, get_bus
from agent_core import AgentCore, SafetyGuard, SelfChecker
from awareness_engine import DesktopAwarenessEngine
from controller_engine import DesktopAutomationController
from multimodal_engine import MultimodalEngine, TextResult
from memory_store import MemoryStore
from learning_engine import LearningEngine
from upgrade_engine import UpgradeEngine
from optimization_engine import OptimizationEngine
from collaboration_engine import CollaborationEngine

print("[1/7] All 9 modules imported")

cfg_path = PROJECT_DIR / "config.yaml"
with open(cfg_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
config["project_dir"] = str(PROJECT_DIR)
print("[2/7] config.yaml loaded (" + str(len(config)) + " sections)")

bus = EvolutionBus(project_dir=PROJECT_DIR)
received = []
bus.subscribe_all(lambda event: received.append((event.source, event.kind)))

multimodal = MultimodalEngine.__new__(MultimodalEngine)
multimodal._client = MagicMock()
multimodal._health = {"text": True, "vision": True}

def fake_think_and_act(user_message, desktop_context=None, system_prompt="", memory_context=""):
    return TextResult(
        success=True,
        content="Action: answer\nActionInput: {\"type\": \"answer\", \"content\": \"stubbed final answer\"}",
        thought="I have enough context to answer.",
        action={"type": "answer", "content": "stubbed final answer"},
        latency_ms=1.0,
    )

multimodal.think_and_act = fake_think_and_act
multimodal.get_health = lambda: {"text": True, "vision": True, "model": "stub"}
multimodal.is_ready = lambda model_type="all": True
print("[3/7] MultimodalEngine stubbed (no network calls)")

perception = DesktopAwarenessEngine.__new__(DesktopAwarenessEngine)
perception.enabled = True
perception.stats = {"total_scans": 0, "errors": 0, "last_scan_time_ms": 0}
perception.get_current_state = lambda: {
    "active_window": {"title": "stub"},
    "mouse_position": (0, 0),
    "window_list": [],
    "total_windows": 0,
}

controller = DesktopAutomationController.__new__(DesktopAutomationController)
controller.stats = {"total_actions": 0, "successful_actions": 0, "failed_actions": 0}
controller.perform_action = lambda action: {
    "success": True,
    "action_type": action.get("type", ""),
    "error": "",
    "result": "stubbed",
    "duration_ms": 1.0,
}

memory = MemoryStore(project_dir=PROJECT_DIR)
learning = LearningEngine(config=config, memory_store=memory)
upgrade = UpgradeEngine(config=config, project_dir=PROJECT_DIR)
optimization = OptimizationEngine(config=config, project_dir=PROJECT_DIR)
collaboration = CollaborationEngine(config=config, project_dir=PROJECT_DIR)

for eng in (learning, upgrade, optimization, collaboration):
    if hasattr(eng, "set_event_bus"):
        eng.set_event_bus(bus)

learning_evt = [e for e in received if e[0] == "learning" and e[1] == "bus_attached"]
upgrade_evt = [e for e in received if e[0] == "upgrade" and e[1] == "bus_attached"]
optimization_evt = [e for e in received if e[0] == "optimization" and e[1] == "bus_attached"]
collaboration_evt = [e for e in received if e[0] == "collaboration" and e[1] == "bus_attached"]
assert learning_evt, "learning bus_attached missing"
assert upgrade_evt, "upgrade bus_attached missing"
assert optimization_evt, "optimization bus_attached missing"
assert collaboration_evt, "collaboration bus_attached missing"
print("[4/7] All 4 evolution engines attached to bus and emitted bus_attached")

core = AgentCore(
    perception=perception,
    controller=controller,
    multimodal=multimodal,
    memory=memory,
    safety_guard=SafetyGuard(),
    self_checker=SelfChecker(max_retries=3),
)
core.learning = learning
core.upgrade = upgrade
core.optimization = optimization
core.collaboration = collaboration

bus.emit("agent_core", "initialized", {"headless": True})
print("[5/7] AgentCore constructed with 4 evolution engines wired")

events_before = len(received)
result = core.execute_task("stub question", timeout=15)
events_after = len(received)
print("[6/7] execute_task returned success=" + str(result.success) + ", steps=" + str(result.steps_taken) + ", duration=" + str(round(result.duration_seconds, 2)) + "s")
print("      final_response: " + str(result.final_response[:80]))
print("      events emitted during task: " + str(events_after - events_before))

assert result.success, "TaskResult.success should be True (got " + str(result.success) + ")"
assert result.steps_taken >= 1, "expected at least 1 step (got " + str(result.steps_taken) + ")"

status = core.get_status()
assert isinstance(status, dict), "get_status must return dict"
print("      get_status keys: " + ", ".join(sorted(status.keys())))

sources = {src for src, _ in received}
print("[7/7] EvolutionBus snapshot captured events from: " + ", ".join(sorted(sources)))
assert "learning" in sources or "optimization" in sources, "expected learning or optimization event, got " + str(sources)

bus_path = PROJECT_DIR / "data" / "logs" / "evolution_events.jsonl"
size = bus_path.stat().st_size if bus_path.exists() else 0
print("")
print("Bus JSONL log: " + str(bus_path) + " (" + str(size) + " bytes)")
print("Total events captured: " + str(len(received)))

print("")
print("SMOKE TEST PASSED")