# -*- coding: utf-8 -*-
"""
start_remote.py - 启动远控 API（端口 9999）

把所有引擎（感知/控制/多模态/记忆/协作/学习/升级/优化）串起来，
启动 HTTP 服务，让外部 AI 通过 REST 接口调用本 Agent。
"""

import sys
import time
import signal
import logging
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

from evolution_bus import EvolutionBus
from awareness_engine import DesktopAwarenessEngine
from controller_engine import DesktopAutomationController
from multimodal_engine import MultimodalEngine
from memory_store import MemoryStore
from collaboration_engine import CollaborationEngine
from learning_engine import LearningEngine
from upgrade_engine import UpgradeEngine
from optimization_engine import OptimizationEngine
from agent_core import AgentCore
from remote_control import start_remote_control

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("start_remote")


def load_config() -> dict:
    with open(PROJECT_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    log.info("=" * 60)
    log.info("桌面 AI Agent - 远控服务启动")
    log.info("=" * 60)

    cfg = load_config()

    # 1) 事件总线
    bus = EvolutionBus(project_dir=PROJECT_DIR)

    # 2) 基础引擎
    log.info("初始化感知引擎...")
    perception = DesktopAwarenessEngine(
        capture_fps=cfg["awareness"]["capture_fps"],
        resolution=cfg["awareness"]["resolution"],
    )

    log.info("初始化控制引擎...")
    controller = DesktopAutomationController(
        click_delay=cfg["control"]["click_delay"],
        type_speed=cfg["control"]["type_speed"],
    )

    log.info("初始化多模态引擎...")
    multimodal = MultimodalEngine(
        text_port=cfg["llama_cpp"]["text_model"]["port"],
        vision_port=cfg["llama_cpp"]["vision_model"]["port"],
    )

    log.info("初始化记忆存储...")
    memory = MemoryStore(project_dir=PROJECT_DIR)

    # 3) 协作 / 学习 / 升级 / 优化
    log.info("初始化协作引擎...")
    collaboration = CollaborationEngine(
        cfg["evolution"]["collaboration"],
        project_dir=PROJECT_DIR,
    )

    log.info("初始化学习引擎...")
    learning = LearningEngine(
        cfg["evolution"]["learning"],
        memory_store=memory,
    )
    learning.set_event_bus(bus)

    log.info("初始化升级引擎...")
    upgrade = UpgradeEngine(
        cfg["evolution"]["upgrade"],
        project_dir=PROJECT_DIR,
    )
    upgrade.set_event_bus(bus)

    log.info("初始化优化引擎...")
    optimization = OptimizationEngine(
        cfg["evolution"]["optimization"],
        project_dir=PROJECT_DIR,
    )
    optimization.set_event_bus(bus)

    # 4) AgentCore
    log.info("初始化 AgentCore...")
    agent_core = AgentCore(
        perception=perception,
        controller=controller,
        multimodal=multimodal,
        memory=memory,
    )

    # 5) 启动远控
    log.info("启动远控 HTTP API: http://127.0.0.1:9999")
    system = start_remote_control(
        port=9999,
        host="127.0.0.1",
        agent_core=agent_core,
        perception=perception,
        controller=controller,
        memory=memory,
        optimization=optimization,
        collaboration=collaboration,
    )

    log.info("服务就绪。Ctrl+C 退出。")
    log.info("可用指令示例:")
    log.info("  GET  /api/health")
    log.info("  GET  /api/status")
    log.info("  POST /api/command  body={\"command\":\"agent_chat\",\"params\":{\"message\":\"你好\"}}")

    stop_flag = {"stop": False}

    def _shutdown(signum, frame):
        log.info("收到退出信号 (%s)，正在关闭...", signum)
        stop_flag["stop"] = True

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop_flag["stop"]:
            time.sleep(1)
    finally:
        log.info("停止远控服务...")
        try:
            system.stop_server()
        except Exception as e:
            log.warning("关闭异常: %s", e)


if __name__ == "__main__":
    main()
