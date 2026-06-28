"""
优化引擎 (Optimization Engine) — Agent的"神经系统"
负责：性能监控、策略调优、资源调度、自我反思

核心能力：
1. 性能自优化 — 实时监控响应速度、资源使用、决策质量
2. 策略自优化 — 每次任务后反思，优化ReAct循环和参数
3. 资源自优化 — 根据GPU显存动态调整模型加载
4. 决策自优化 — 记录成功/失败案例，改进决策逻辑
"""
import json
import time
import psutil
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import deque


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class PerformanceMetric:
    """性能指标"""
    timestamp: str
    metric_name: str
    value: float
    unit: str  # ms / GB / % / count
    context: str = ""  # 附加上下文


@dataclass
class TaskRecord:
    """任务执行记录"""
    task_id: str
    description: str
    start_time: str
    end_time: str
    duration_sec: float
    steps_taken: int
    success: bool
    model_used: str
    tokens_generated: int = 0
    vram_peak_gb: float = 0.0
    memory_peak_gb: float = 0.0
    error_message: str = ""
    reflection: str = ""  # 任务后的反思


@dataclass
class StrategyUpdate:
    """策略更新记录"""
    timestamp: str
    strategy_name: str
    old_value: Any
    new_value: Any
    reason: str
    improvement: float = 0.0  # 改进百分比


@dataclass
class ResourceSchedule:
    """资源调度记录"""
    timestamp: str
    action: str  # load / unload / swap
    model_name: str
    category: str
    vram_before_gb: float
    vram_after_gb: float
    reason: str


# ---------------------------------------------------------------------------
# 优化引擎主类
# ---------------------------------------------------------------------------

class OptimizationEngine:
    """
    Agent的优化引擎 — 让Agent持续变快的关键组件
    
    工作流程：
    1. 实时监控性能指标
    2. 每次任务后自动反思
    3. 发现瓶颈则调整策略
    4. 根据资源使用情况动态调度
    """
    
    def __init__(self, config: Dict[str, Any], project_dir: Path = None):
        self.config = config.get("evolution", {}).get("optimization", {})
        self.performance_monitoring = self.config.get("performance_monitoring", True)
        self.auto_resource_scheduling = self.config.get("auto_resource_scheduling", True)
        self.strategy_reflection = self.config.get("strategy_reflection", True)
        self.max_reflection_history = self.config.get("max_reflection_history", 1000)
        
        self.project_dir = project_dir or Path(config.get("project_dir", r"E:\Desktop\AI_Agent"))
        self.logs_dir = self.project_dir / "data" / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存缓存
        self._metrics: deque = deque(maxlen=10000)
        self._task_records: List[TaskRecord] = []
        self._strategy_updates: List[StrategyUpdate] = []
        self._resource_schedules: List[ResourceSchedule] = []
        self._reflection_log: List[Dict] = []
        
        # 性能基线（首次任务后建立）
        self._baseline = {
            "response_time_ms": None,
            "vram_usage_gb": None,
            "memory_usage_gb": None,
            "cpu_usage_percent": None,
        }
        
        # 实时监控线程
        self._monitoring = False
        self._monitor_thread = None
        
        # 加载已有数据
        self._load_all()

        # Phase 2 — 事件总线
        self._event_bus = None
    
    # ------------------------------------------------------------------
    # 性能监控
    # ------------------------------------------------------------------
    
    def start_monitoring(self):
        """启动后台性能监控"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self):
        """停止后台监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """后台监控循环 — 每秒采集一次系统资源"""
        while self._monitoring:
            try:
                # CPU
                cpu_percent = psutil.cpu_percent(interval=1)
                self.record_metric("cpu_usage", cpu_percent, "%", "system")
                
                # 内存
                mem = psutil.virtual_memory()
                self.record_metric("memory_usage", mem.percent / 100 * (mem.total / 1024**3), "GB", "system")
                
                # GPU（如果有nvidia-smi）
                try:
                    import subprocess
                    result = subprocess.run(
                        ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.returncode == 0:
                        gpu_line = result.stdout.strip().split("\n")[0]
                        used, total = map(float, gpu_line.split(","))
                        self.record_metric("gpu_vram_used", used / 1024, "GB", "gpu")
                        self.record_metric("gpu_vram_total", total / 1024, "GB", "gpu")
                except Exception:
                    pass
                
            except Exception:
                pass
            
            time.sleep(1)
    
    def record_metric(self, name: str, value: float, unit: str, context: str = ""):
        """记录性能指标"""
        metric = PerformanceMetric(
            timestamp=datetime.now().isoformat(),
            metric_name=name,
            value=value,
            unit=unit,
            context=context,
        )
        self._metrics.append(asdict(metric))
    
    def record_task_start(self, task_id: str, description: str) -> str:
        """记录任务开始"""
        return task_id
    
    def record_task_end(self, task_id: str, description: str, duration_sec: float,
                       steps_taken: int, success: bool, model_used: str,
                       tokens_generated: int = 0, error_message: str = ""):
        """
        记录任务完成
        
        同时触发反思和优化
        """
        # 获取峰值资源使用
        vram_peak = self._get_current_vram()
        memory_peak = psutil.Process().memory_info().rss / (1024 ** 3)
        
        record = TaskRecord(
            task_id=task_id,
            description=description,
            start_time=datetime.now().isoformat(),
            end_time=datetime.now().isoformat(),
            duration_sec=duration_sec,
            steps_taken=steps_taken,
            success=success,
            model_used=model_used,
            tokens_generated=tokens_generated,
            vram_peak_gb=vram_peak,
            memory_peak_gb=memory_peak,
            error_message=error_message,
        )
        
        self._task_records.append(record)
        
        # 触发反思（如果启用）
        if self.strategy_reflection:
            self._reflect_on_task(record)
        
        # 更新基线
        self._update_baseline(record)
        
        # 持久化
        self._save_tasks()
    
    def _get_current_vram(self) -> float:
        """获取当前GPU显存使用量(GB)"""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return float(result.stdout.strip()) / 1024
        except Exception:
            pass
        return 0.0
    
    # ------------------------------------------------------------------
    # 策略自优化（反思）
    # ------------------------------------------------------------------
    
    def _reflect_on_task(self, task: TaskRecord):
        """
        对任务进行反思
        
        分析：
        1. 任务是否高效完成？
        2. 哪一步可以优化？
        3. 下次遇到类似任务怎么改进？
        """
        reflection = {
            "task_id": task.task_id,
            "description": task.description,
            "timestamp": datetime.now().isoformat(),
            "analysis": {},
            "suggestions": [],
        }
        
        # 分析1: 速度评估
        if task.duration_sec > 60:  # 超过60秒算慢
            reflection["analysis"]["speed"] = "slow"
            reflection["suggestions"].append("任务耗时较长，考虑简化流程或使用缓存")
        elif task.duration_sec < 5:  # 少于5秒算快
            reflection["analysis"]["speed"] = "fast"
        else:
            reflection["analysis"]["speed"] = "normal"
        
        # 分析2: 步骤效率
        if task.steps_taken > 5 and task.success:
            reflection["suggestions"].append(f"用了{task.steps_taken}步完成任务，可能有更简洁的方法")
        elif task.steps_taken > 10:
            reflection["suggestions"].append(f"步骤过多({task.steps_taken})，考虑使用预存技能")
        
        # 分析3: 资源使用
        if task.vram_peak_gb > 14:  # 接近16GB上限
            reflection["suggestions"].append("显存使用过高，考虑卸载不需要的模型")
        
        # 分析4: 失败分析
        if not task.success:
            reflection["analysis"]["result"] = "failed"
            reflection["suggestions"].append(f"任务失败: {task.error_message}")
            reflection["suggestions"].append("记录失败模式，下次避免相同错误")
        else:
            reflection["analysis"]["result"] = "success"
        
        # 保存反思
        self._reflection_log.append(reflection)
        
        # 限制历史记录
        if len(self._reflection_log) > self.max_reflection_history:
            self._reflection_log = self._reflection_log[-self.max_reflection_history:]
        
        self._save_reflections()
    
    def _update_baseline(self, task: TaskRecord):
        """更新性能基线"""
        if self._baseline["response_time_ms"] is None:
            self._baseline["response_time_ms"] = task.duration_sec * 1000
        
        # 移动平均更新
        alpha = 0.1  # 平滑因子
        current = self._baseline["response_time_ms"]
        new = task.duration_sec * 1000
        self._baseline["response_time_ms"] = current * (1 - alpha) + new * alpha
    
    # ------------------------------------------------------------------
    # 资源自优化
    # ------------------------------------------------------------------
    
    def optimize_resource_allocation(self, task_type: str = "text") -> Dict[str, Any]:
        """
        根据任务类型优化资源分配
        
        策略：
        1. 文本任务 → 只加载文本模型
        2. 视觉任务 → 只加载视觉模型
        3. 文本+视觉 → 同时加载两个模型
        4. 空闲时 → 全部卸载
        """
        schedule = {
            "task_type": task_type,
            "actions": [],
            "vram_before_gb": self._get_current_vram(),
            "expected_vram_after_gb": 0,
        }
        
        if task_type == "idle":
            # 空闲时卸载所有模型
            schedule["actions"] = [
                {"action": "unload_all", "reason": "系统空闲，释放显存"}
            ]
            schedule["expected_vram_after_gb"] = 0
        
        elif task_type == "text":
            # 只加载文本模型
            schedule["actions"] = [
                {"action": "unload_vision_model", "reason": "只需要文本推理"},
                {"action": "load_text_model", "reason": "Hermes-3-8B约5.5GB"},
            ]
            schedule["expected_vram_after_gb"] = 5.5
        
        elif task_type == "vision":
            # 只加载视觉模型
            schedule["actions"] = [
                {"action": "unload_text_model", "reason": "只需要视觉理解"},
                {"action": "load_vision_model", "reason": "Qwen2.5-VL-7B约6.5GB"},
            ]
            schedule["expected_vram_after_gb"] = 6.5
        
        elif task_type == "text+vision":
            # 同时加载
            schedule["actions"] = [
                {"action": "load_both_models", "reason": "需要文本+视觉"},
            ]
            schedule["expected_vram_after_gb"] = 12.0
        
        elif task_type == "video":
            # 视频理解
            schedule["actions"] = [
                {"action": "unload_vision_model", "reason": "替换为视频模型"},
                {"action": "load_llava_video", "reason": "LLaVA-NeXT-Video约8GB"},
            ]
            schedule["expected_vram_after_gb"] = 13.5
        
        # 记录调度
        for action in schedule["actions"]:
            self._resource_schedules.append(ResourceSchedule(
                timestamp=datetime.now().isoformat(),
                action=action["action"],
                model_name="",
                category=task_type,
                vram_before_gb=schedule["vram_before_gb"],
                vram_after_gb=schedule["expected_vram_after_gb"],
                reason=action["reason"],
            ))
        
        self._save_resource_schedule()
        return schedule
    
    # ------------------------------------------------------------------
    # 策略调优
    # ------------------------------------------------------------------
    
    def suggest_strategy_improvements(self) -> List[Dict]:
        """
        基于历史数据提出策略改进建议
        
        分析：
        1. 哪些任务经常失败？
        2. 哪些任务特别慢？
        3. 有没有重复的成功模式可以固化？
        """
        suggestions = []
        
        if not self._task_records:
            return suggestions
        
        # 分析1: 失败率高的任务类型
        task_outcomes = {}
        for task in self._task_records:
            # 按描述的前几个词分类
            key = task.description[:20]
            if key not in task_outcomes:
                task_outcomes[key] = {"total": 0, "success": 0, "failures": []}
            task_outcomes[key]["total"] += 1
            if task.success:
                task_outcomes[key]["success"] += 1
            else:
                task_outcomes[key]["failures"].append(task.task_id)
        
        for key, data in task_outcomes.items():
            if data["total"] >= 3:
                success_rate = data["success"] / data["total"]
                if success_rate < 0.7:
                    suggestions.append({
                        "type": "high_failure_rate",
                        "task_pattern": key,
                        "success_rate": round(success_rate, 2),
                        "total_attempts": data["total"],
                        "suggestion": f"任务模式'{key}'失败率较高({success_rate:.0%})，建议优化该任务的执行策略",
                    })
        
        # 分析2: 慢任务的模式
        slow_tasks = [t for t in self._task_records if t.duration_sec > 30]
        if slow_tasks:
            avg_duration = sum(t.duration_sec for t in slow_tasks) / len(slow_tasks)
            suggestions.append({
                "type": "slow_tasks",
                "count": len(slow_tasks),
                "avg_duration_sec": round(avg_duration, 1),
                "suggestion": f"发现{len(slow_tasks)}个慢任务(平均{avg_duration:.1f}s)，考虑缓存或预计算",
            })
        
        # 分析3: 成功的重复模式 → 固化为技能
        successful_steps = {}
        for task in self._task_records:
            if task.success and task.steps_taken <= 5:
                key = task.description[:30]
                if key not in successful_steps:
                    successful_steps[key] = []
                successful_steps[key].append(task.steps_taken)
        
        for key, steps_list in successful_steps.items():
            if len(steps_list) >= 3:
                avg_steps = sum(steps_list) / len(steps_list)
                suggestions.append({
                    "type": "repeatable_success",
                    "task_pattern": key,
                    "avg_steps": round(avg_steps, 1),
                    "occurrences": len(steps_list),
                    "suggestion": f"任务模式'{key}'多次成功({len(steps_list)}次)，建议固化为技能",
                })
        
        return suggestions
    
    def apply_strategy_improvement(self, suggestion: Dict):
        """应用策略改进建议"""
        if suggestion["type"] == "repeatable_success":
            # 记录为成功模式
            update = StrategyUpdate(
                timestamp=datetime.now().isoformat(),
                strategy_name="skill_formation",
                old_value=None,
                new_value=suggestion["task_pattern"],
                reason=f"将成功模式固化为技能: {suggestion['task_pattern']}",
                improvement=suggestion.get("occurrences", 0) * 10,
            )
            self._strategy_updates.append(update)
            self._save_strategies()
    
    # ------------------------------------------------------------------
    # 数据持久化
    # ------------------------------------------------------------------
    
    def _load_all(self):
        """加载所有已保存的数据"""
        # 加载任务记录
        tasks_file = self.logs_dir / "task_records.json"
        if tasks_file.exists():
            try:
                data = json.loads(tasks_file.read_text(encoding="utf-8"))
                for t in data:
                    self._task_records.append(TaskRecord(**t))
            except Exception:
                pass
        
        # 加载反思记录
        reflections_file = self.logs_dir / "reflections.json"
        if reflections_file.exists():
            try:
                self._reflection_log = json.loads(reflections_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        # 加载策略更新
        strategies_file = self.logs_dir / "strategy_updates.json"
        if strategies_file.exists():
            try:
                data = json.loads(strategies_file.read_text(encoding="utf-8"))
                for s in data:
                    self._strategy_updates.append(StrategyUpdate(**s))
            except Exception:
                pass
    
    def _save_tasks(self):
        """保存任务记录"""
        file = self.logs_dir / "task_records.json"
        try:
            data = [asdict(t) for t in self._task_records[-self.max_reflection_history:]]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _save_reflections(self):
        """保存反思记录"""
        file = self.logs_dir / "reflections.json"
        try:
            file.write_text(
                json.dumps(self._reflection_log[-self.max_reflection_history:], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    
    def _save_strategies(self):
        """保存策略更新"""
        file = self.logs_dir / "strategy_updates.json"
        try:
            data = [asdict(s) for s in self._strategy_updates]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def _save_resource_schedule(self):
        """保存资源调度记录"""
        file = self.logs_dir / "resource_schedule.json"
        try:
            data = [asdict(s) for s in self._resource_schedules[-100:]]
            file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    # ------------------------------------------------------------------
    # 统计信息
    # ------------------------------------------------------------------
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表盘数据"""
        total_tasks = len(self._task_records)
        successful_tasks = sum(1 for t in self._task_records if t.success)
        avg_duration = 0
        if total_tasks > 0:
            avg_duration = sum(t.duration_sec for t in self._task_records) / total_tasks
        
        # 最近性能指标
        recent_metrics = {}
        if self._metrics:
            metrics_list = list(self._metrics)
            # 取最近的每项指标
            for m in metrics_list[-100:]:
                name = m["metric_name"]
                recent_metrics[name] = m["value"]
        
        return {
            "total_tasks": total_tasks,
            "successful_tasks": successful_tasks,
            "success_rate": round(successful_tasks / max(total_tasks, 1), 3),
            "avg_duration_sec": round(avg_duration, 2),
            "current_vram_gb": round(self._get_current_vram(), 2),
            "current_cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
            "current_memory_gb": round(psutil.Process().memory_info().rss / (1024 ** 3), 2),
            "recent_metrics": recent_metrics,
            "baseline_response_time_ms": round(self._baseline["response_time_ms"] or 0, 1),
            "reflection_count": len(self._reflection_log),
            "strategy_updates": len(self._strategy_updates),
        }
    
    def get_performance_trend(self, hours: int = 24) -> List[Dict]:
        """获取性能趋势（最近N小时）"""
        cutoff = datetime.now() - timedelta(hours=hours)
        trend = []
        
        for task in self._task_records:
            task_time = datetime.fromisoformat(task.start_time)
            if task_time >= cutoff:
                trend.append({
                    "time": task.start_time,
                    "duration_sec": task.duration_sec,
                    "success": task.success,
                    "steps": task.steps_taken,
                })
        
        return trend
    def get_performance_report(self) -> Dict[str, Any]:
        """性能报告 (供远控 API /api/performance 使用)"""
        try:
            data = self.get_dashboard_data()
        except Exception as e:
            return {"error": f"dashboard_error: {e}"}
        try:
            data["performance_trend"] = self.get_performance_trend(hours=24)
        except Exception as e:
            data["performance_trend_error"] = str(e)
        data["report_generated_at"] = datetime.now().isoformat()
        return data


    # ------------------------------------------------------------------
    # Phase 2 增强 — 事件总线接入
    # ------------------------------------------------------------------

    def set_event_bus(self, bus) -> None:
        """注入事件总线"""
        self._event_bus = bus
        if self._event_bus:
            self._event_bus.emit("optimization", "bus_attached", {
                "reflection_history": len(self._reflection_log),
                "task_records": len(self._task_records),
            })

    def record_task_end(self, task_id: str, description: str, duration_sec: float,
                       steps_taken: int, success: bool, model_used: str,
                       tokens_generated: int = 0, error_message: str = "") -> None:
        """覆盖父类同名方法 — 在结束时发出事件"""
        super_method = getattr(super(), "record_task_end", None)
        if super_method:
            try:
                super_method(task_id, description, duration_sec, steps_taken,
                             success, model_used, tokens_generated, error_message)
            except Exception:
                pass
        if self._event_bus:
            self._event_bus.emit("optimization", "task_completed", {
                "task_id": task_id, "duration_sec": round(duration_sec, 2),
                "steps": steps_taken, "success": success, "model": model_used,
            })
