"""
桌面 AI Agent — 主入口 (v3.0)
===========================
构造全部 8 个引擎，注入 AgentCore，提供 CLI 调试模式与 GUI 启动。
"""
import sys
import os
import json
import time
import logging
import argparse
from pathlib import Path

# 让 import 能找到当前目录
sys.path.insert(0, str(Path(__file__).parent))

import yaml

# 业务模块（按依赖顺序）
from agent_core import AgentCore, SafetyGuard, SelfChecker, AgentStatus
from awareness_engine import DesktopAwarenessEngine
from controller_engine import DesktopAutomationController
from multimodal_engine import MultimodalEngine
from memory_store import MemoryStore
from learning_engine import LearningEngine
from upgrade_engine import UpgradeEngine
from optimization_engine import OptimizationEngine
from collaboration_engine import CollaborationEngine

from evolution_bus import EvolutionBus, get_bus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def load_config(project_dir: Path) -> dict:
    cfg_path = project_dir / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"config.yaml 不存在: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["project_dir"] = str(project_dir)
    return cfg


def build_agent_core(project_dir: Path, config: dict, bus: EvolutionBus, headless: bool = True):
    """构造 AgentCore 并接入全部引擎"""
    logger.info("构造 8 个引擎 ...")

    perception = DesktopAwarenessEngine()
    controller = DesktopAutomationController()
    multimodal = MultimodalEngine(
        text_port=config["llama_cpp"]["text_model"]["port"],
        vision_port=config["llama_cpp"]["vision_model"]["port"],
    )
    memory = MemoryStore(project_dir=project_dir)

    learning = LearningEngine(config=config, memory_store=memory)
    upgrade = UpgradeEngine(config=config, project_dir=project_dir)
    optimization = OptimizationEngine(config=config, project_dir=project_dir)
    collaboration = CollaborationEngine(config=config, project_dir=project_dir)

    # 把事件总线注入每个引擎（如果引擎支持）
    for eng in (learning, upgrade, optimization, collaboration):
        if hasattr(eng, "set_event_bus"):
            eng.set_event_bus(bus)

    core = AgentCore(
        perception=perception,
        controller=controller,
        multimodal=multimodal,
        memory=memory,
        safety_guard=SafetyGuard(),
        self_checker=SelfChecker(max_retries=3),
    )

    # 把 4 个进化引擎挂到 core 上，供 execute_task 调用
    core.learning = learning
    core.upgrade = upgrade
    core.optimization = optimization
    core.collaboration = collaboration

    # 在 headless 模式下，给 multimodal 装一个 get_health 桩，方便干跑
    if headless:
        multimodal.get_health = lambda: {"text": True, "vision": True}

    # 记录初始事件
    bus.emit("agent_core", "initialized", {
        "engines": ["perception", "controller", "multimodal", "memory",
                    "learning", "upgrade", "optimization", "collaboration"],
        "headless": headless,
    })

    return core


def run_cli(core: AgentCore, bus: EvolutionBus):
    """交互式 REPL"""
    print()
    print("=" * 60)
    print("桌面 AI Agent — CLI 模式")
    print("输入任务指令回车执行；输入 :quit 退出；输入 :stats 看状态")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input in (":quit", ":exit"):
            break
        if user_input == ":stats":
            print(json.dumps(bus.snapshot(), ensure_ascii=False, indent=2))
            print(json.dumps(core.get_status(), ensure_ascii=False, indent=2))
            continue
        if user_input == ":help":
            print("可用指令:")
            print("  <任意文本>          发送给 AgentCore 执行")
            print("  :stats              查看事件总线和 Agent 状态")
            print("  :health             查看 LLM 服务健康状态")
            print("  :recent             查看最近 10 条事件")
            print("  :quit / :exit       退出")
            continue
        if user_input == ":health":
            health = core.multimodal.get_health()
            print(json.dumps(health, ensure_ascii=False, indent=2))
            continue
        if user_input == ":recent":
            for e in bus.recent(limit=10):
                print(f"  [{e.timestamp}] {e.source}/{e.kind}: {e.payload}")
            continue

        # 真正执行任务
        t0 = time.time()
        result = core.execute_task(user_input)
        dt = time.time() - t0

        print()
        print(f"--- result ({dt:.1f}s, success={result.success}, steps={result.steps_taken}) ---")
        if result.final_response:
            print(result.final_response)
        if result.errors:
            print("errors:")
            for e in result.errors[:5]:
                print(f"  - {e}")
        if result.reflections:
            print("reflections:")
            for r in result.reflections[:3]:
                print(f"  - {r}")
        print()

    print("bye.")


def run_one_shot(core: AgentCore, message: str):
    """单条指令模式，用于测试或脚本调用"""
    logger.info(f"单次执行: {message}")
    result = core.execute_task(message)
    print(json.dumps({
        "success": result.success,
        "task_id": result.task_id,
        "steps": result.steps_taken,
        "duration": round(result.duration_seconds, 2),
        "response": result.final_response,
        "errors": result.errors,
    }, ensure_ascii=False, indent=2))
    return result


def run_gui(core: AgentCore):
    """启动 PyQt6 主界面"""
    try:
        from ui_main import MainWindow
        from PyQt6.QtWidgets import QApplication
    except ImportError as e:
        logger.error(f"PyQt6 不可用: {e}")
        logger.error("改用 CLI 模式。pip install PyQt6 之后重试。")
        return run_cli(core, get_bus())

    app = QApplication(sys.argv)
    window = MainWindow(core)
    window.show()
    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(description="桌面 AI Agent 主入口")
    parser.add_argument("--project-dir", default=str(Path(__file__).parent),
                        help="项目目录 (默认: 脚本所在目录)")
    parser.add_argument("--gui", action="store_true", help="启动 PyQt6 主界面")
    parser.add_argument("--message", "-m", help="单条指令模式: 执行后退出")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式 (跳过对 LLM 服务的实时健康检查)")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    os.chdir(project_dir)

    config = load_config(project_dir)
    bus = get_bus(project_dir)

    core = build_agent_core(project_dir, config, bus, headless=args.headless or bool(args.message))

    if args.gui:
        run_gui(core)
    elif args.message:
        run_one_shot(core, args.message)
    else:
        run_cli(core, bus)


if __name__ == "__main__":
    main()