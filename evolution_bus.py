"""
进化事件总线 (Evolution Event Bus)
=================================
各引擎通过这个总线发布事件，进化仪表盘订阅事件刷新数据。
设计原则：极简、解耦、线程安全。
"""
import json
import threading
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Callable, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class EvolutionEvent:
    """一条进化事件"""
    source: str
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat(timespec="seconds")


class EvolutionBus:
    """全局事件总线"""

    def __init__(self, project_dir: Path = None):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._event_log: List[EvolutionEvent] = []
        self._max_log = 500
        self.project_dir = project_dir or Path(r"C:\Users\Administrator\Desktop\AI_Agent")
        self.log_file = self.project_dir / "data" / "logs" / "evolution_events.jsonl"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def subscribe(self, kind: str, callback: Callable) -> None:
        """订阅指定类型的事件"""
        with self._lock:
            self._subscribers[kind].append(callback)

    def subscribe_all(self, callback: Callable) -> None:
        """订阅所有事件"""
        with self._lock:
            self._subscribers["*"].append(callback)

    def emit(self, source: str, kind: str, payload: Dict[str, Any] = None) -> None:
        """发布事件"""
        event = EvolutionEvent(source=source, kind=kind, payload=payload or {})
        with self._lock:
            self._event_log.append(event)
            if len(self._event_log) > self._max_log:
                self._event_log = self._event_log[-self._max_log:]
            callbacks = list(self._subscribers.get(kind, [])) + list(self._subscribers.get("*", []))
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        except Exception:
            pass
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass

    def recent(self, kind: str = None, limit: int = 20) -> List[EvolutionEvent]:
        """获取最近的事件"""
        with self._lock:
            events = list(self._event_log)
        if kind:
            events = [e for e in events if e.kind == kind]
        return events[-limit:]

    def snapshot(self) -> Dict[str, Any]:
        """给仪表盘的当前快照"""
        by_source: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        with self._lock:
            for e in self._event_log:
                by_source[e.source][e.kind] += 1
        return {
            "total_events": len(self._event_log),
            "by_source": {s: dict(k) for s, k in by_source.items()},
            "last_event_at": self._event_log[-1].timestamp if self._event_log else "",
        }


_bus_instance: EvolutionBus = None


def get_bus(project_dir: Path = None) -> EvolutionBus:
    """获取全局事件总线单例"""
    global _bus_instance
    if _bus_instance is None:
        _bus_instance = EvolutionBus(project_dir)
    return _bus_instance