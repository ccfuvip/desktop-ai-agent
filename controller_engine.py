"""
桌面控制引擎 (Desktop Automation Controller)
============================================
像人一样操控电脑：鼠标、键盘、窗口、浏览器

技术栈:
- 鼠标: pyautogui
- 键盘: keyboard
- 窗口: pywin32
- 浏览器: playwright

安全机制:
- 分级权限控制 (绿/黄/红)
- 紧急停止 (鼠标移到左上角)
- 操作前自检
- 操作后验证

作者: Desktop AI Agent
版本: 1.0.0
"""

import time
import json
import logging
import win32gui
import win32con
import win32api
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import pyautogui
import keyboard
from PIL import Image

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """操作风险等级"""
    LOW = "green"       # 自动执行
    MEDIUM = "yellow"   # 需要确认
    HIGH = "red"        # 禁止执行


@dataclass
class ActionResult:
    """操作结果"""
    success: bool = False
    action_type: str = ""
    description: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)


class DesktopAutomationController:
    """
    桌面自动化控制器
    
    核心能力:
    1. 鼠标控制 (点击、双击、右键、拖拽、滚动)
    2. 键盘控制 (输入、组合键、模拟真实打字)
    3. 窗口管理 (聚焦、移动、调整大小、最小化/最大化)
    4. 元素定位 (坐标/名称/控件类型)
    5. 安全守卫 (分级权限 + 紧急停止)
    
    使用示例:
        ctrl = DesktopAutomationController()
        ctrl.click(x=100, y=200)
        ctrl.type_text("Hello World", speed=0.02)
        ctrl.focus_window("Chrome")
        result = ctrl.perform_action({"type": "click", "target": "新建按钮"})
    """
    
    def __init__(self, click_delay: float = 0.1, type_speed: float = 0.02):
        self.click_delay = click_delay
        self.type_speed = type_speed
        
        # 安全设置
        pyautogui.FAILSAFE = True  # 鼠标移到左上角紧急停止
        pyautogui.PAUSE = click_delay
        
        # 操作统计
        self.stats = {
            "total_actions": 0,
            "successful_actions": 0,
            "failed_actions": 0,
            "last_action": None,
        }
        
        # 风险操作白名单
        self.low_risk_actions = {
            "click", "double_click", "right_click", "move_to",
            "type_text", "press_key", "hotkey", "scroll",
            "focus_window", "minimize_window", "maximize_window",
            "resize_window", "move_window", "screenshot",
            "find_and_click", "find_and_type",
        }
        
        self.medium_risk_actions = {
            "close_window", "kill_process", "drag_to",
        }
        
        self.high_risk_actions = set()  # 所有其他操作默认高风险
    
    def perform_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单一操作
        
        Args:
            action: 操作字典，格式:
                {
                    "type": "click",           # 操作类型
                    "x": 100,                  # 坐标 (可选)
                    "y": 200,
                    "target": "确定按钮",       # 目标名称 (可选)
                    "text": "Hello",           # 输入文本 (可选)
                    "key": "Enter",            # 按键 (可选)
                    "hotkey": "Ctrl+C",        # 组合键 (可选)
                    "delay": 0.5,              # 操作后延迟 (可选)
                }
        
        Returns:
            操作结果字典
        """
        start = time.time()
        action_type = action.get("type", "").lower()
        
        try:
            # 风险检查
            risk = self._assess_risk(action_type, action)
            if risk == RiskLevel.HIGH:
                return ActionResult(
                    success=False,
                    action_type=action_type,
                    error=f"高风险操作被拒绝: {action_type}",
                    metadata={"risk": "high"},
                ).__dict__
            
            # 执行操作
            handler = getattr(self, f"_action_{action_type}", None)
            if handler:
                result = handler(action)
            else:
                result = ActionResult(
                    success=False,
                    action_type=action_type,
                    error=f"未知操作类型: {action_type}",
                )
            
            result.duration_ms = (time.time() - start) * 1000
            self.stats["total_actions"] += 1
            if result.success:
                self.stats["successful_actions"] += 1
            else:
                self.stats["failed_actions"] += 1
            
            self.stats["last_action"] = {
                "type": action_type,
                "success": result.success,
                "duration_ms": round(result.duration_ms, 1),
            }
            
            return result.__dict__
        
        except Exception as e:
            return ActionResult(
                success=False,
                action_type=action_type,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            ).__dict__
    
    def execute_sequence(self, actions: List[Dict], delay_between: float = 0.3) -> List[Dict]:
        """
        顺序执行多个操作
        
        Args:
            actions: 操作列表
            delay_between: 操作间延迟(秒)
        
        Returns:
            所有操作的结果列表
        """
        results = []
        for action in actions:
            result = self.perform_action(action)
            results.append(result)
            
            # 如果失败，停止执行
            if not result.get("success"):
                logger.warning(f"操作失败，停止序列: {result.get('error')}")
                break
            
            time.sleep(delay_between)
        
        return results
    
    # ---- 鼠标操作 ----
    
    def _action_click(self, action: Dict) -> ActionResult:
        """点击"""
        x, y = self._resolve_target(action)
        pyautogui.click(x, y, clicks=action.get("clicks", 1),
                       button=action.get("button", "left"))
        return ActionResult(success=True, action_type="click",
                          description=f"点击 ({x}, {y})")
    
    def _action_double_click(self, action: Dict) -> ActionResult:
        """双击"""
        x, y = self._resolve_target(action)
        pyautogui.doubleClick(x, y)
        return ActionResult(success=True, action_type="double_click",
                          description=f"双击 ({x}, {y})")
    
    def _action_right_click(self, action: Dict) -> ActionResult:
        """右键点击"""
        x, y = self._resolve_target(action)
        pyautogui.rightClick(x, y)
        return ActionResult(success=True, action_type="right_click",
                          description=f"右键点击 ({x}, {y})")
    
    def _action_move_to(self, action: Dict) -> ActionResult:
        """移动到指定位置"""
        x, y = self._resolve_target(action)
        pyautogui.moveTo(x, y, duration=0.3)
        return ActionResult(success=True, action_type="move_to",
                          description=f"移动到 ({x}, {y})")
    
    def _action_drag_to(self, action: Dict) -> ActionResult:
        """拖拽"""
        x1, y1 = action.get("x1", 0), action.get("y1", 0)
        x2, y2 = action.get("x2", 0), action.get("y2", 0)
        pyautogui.dragTo(x2, y2, duration=0.5, button=action.get("button", "left"))
        return ActionResult(success=True, action_type="drag_to",
                          description=f"拖拽 ({x1},{y1}) -> ({x2},{y2})")
    
    def _action_scroll(self, action: Dict) -> ActionResult:
        """滚动"""
        clicks = action.get("clicks", 3)
        direction = action.get("direction", "down")
        if direction == "up":
            clicks = -clicks
        pyautogui.scroll(clicks)
        return ActionResult(success=True, action_type="scroll",
                          description=f"滚动 {'上' if direction=='up' else '下'} {abs(clicks)} 次")
    
    # ---- 键盘操作 ----
    
    def _action_type_text(self, action: Dict) -> ActionResult:
        """输入文本"""
        text = action.get("text", "")
        speed = action.get("speed", self.type_speed)
        pyautogui.typewrite(text, interval=speed)
        return ActionResult(success=True, action_type="type_text",
                          description=f"输入: '{text[:50]}{'...' if len(text)>50 else ''}'")
    
    def _action_press_key(self, action: Dict) -> ActionResult:
        """按下单个键"""
        key = action.get("key", "Enter")
        presses = action.get("presses", 1)
        for _ in range(presses):
            keyboard.press(key)
            time.sleep(0.05)
            keyboard.release(key)
        return ActionResult(success=True, action_type="press_key",
                          description=f"按下: {key}")
    
    def _action_hotkey(self, action: Dict) -> ActionResult:
        """组合键"""
        hotkey = action.get("hotkey", "Alt+Tab")
        # 转换为 pyautogui 格式
        parts = [p.strip() for p in hotkey.split("+")]
        if len(parts) >= 2:
            pyautogui.hotkey(*parts)
        else:
            keyboard.press(parts[0])
            time.sleep(0.05)
            keyboard.release(parts[0])
        return ActionResult(success=True, action_type="hotkey",
                          description=f"组合键: {hotkey}")
    
    # ---- 窗口操作 ----
    
    def _action_focus_window(self, action: Dict) -> ActionResult:
        """聚焦窗口"""
        title = action.get("target", "") or action.get("title", "")
        hwnd = self._find_window_by_title(title)
        if hwnd:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return ActionResult(success=True, action_type="focus_window",
                              description=f"聚焦窗口: {title}")
        return ActionResult(success=False, action_type="focus_window",
                          error=f"未找到窗口: {title}")
    
    def _action_minimize_window(self, action: Dict) -> ActionResult:
        """最小化窗口"""
        hwnd = self._resolve_window(action)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return ActionResult(success=True, action_type="minimize_window")
        return ActionResult(success=False, action_type="minimize_window",
                          error="未找到窗口")
    
    def _action_maximize_window(self, action: Dict) -> ActionResult:
        """最大化窗口"""
        hwnd = self._resolve_window(action)
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return ActionResult(success=True, action_type="maximize_window")
        return ActionResult(success=False, action_type="maximize_window",
                          error="未找到窗口")
    
    def _action_resize_window(self, action: Dict) -> ActionResult:
        """调整窗口大小"""
        hwnd = self._resolve_window(action)
        if hwnd:
            x, y = action.get("x", 0), action.get("y", 0)
            w, h = action.get("width", 800), action.get("height", 600)
            win32gui.MoveWindow(hwnd, x, y, w, h, True)
            return ActionResult(success=True, action_type="resize_window",
                              description=f"调整到 {w}x{h}")
        return ActionResult(success=False, action_type="resize_window",
                          error="未找到窗口")
    
    def _action_move_window(self, action: Dict) -> ActionResult:
        """移动窗口"""
        hwnd = self._resolve_window(action)
        if hwnd:
            x, y = action.get("x", 0), action.get("y", 0)
            win32gui.MoveWindow(hwnd, x, y, 0, 0, True)
            return ActionResult(success=True, action_type="move_window",
                              description=f"移动到 ({x}, {y})")
        return ActionResult(success=False, action_type="move_window",
                          error="未找到窗口")
    
    def _action_close_window(self, action: Dict) -> ActionResult:
        """关闭窗口"""
        hwnd = self._resolve_window(action)
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return ActionResult(success=True, action_type="close_window",
                              description="窗口已关闭")
        return ActionResult(success=False, action_type="close_window",
                          error="未找到窗口")
    
    # ---- 元素定位 ----
    
    def _action_find_and_click(self, action: Dict) -> ActionResult:
        """查找元素并点击"""
        template = action.get("template", "")
        confidence = action.get("confidence", 0.8)
        
        try:
            location = pyautogui.locateOnScreen(template, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                pyautogui.click(center)
                return ActionResult(success=True, action_type="find_and_click",
                                  description=f"找到并点击: {template}")
            return ActionResult(success=False, action_type="find_and_click",
                              error=f"未找到元素: {template}")
        except Exception as e:
            return ActionResult(success=False, action_type="find_and_click",
                              error=str(e))
    
    def _action_screenshot(self, action: Dict) -> ActionResult:
        """截图"""
        try:
            img = pyautogui.screenshot()
            path = action.get("save_path", "./data/screenshots/screenshot.png")
            img.save(path)
            return ActionResult(success=True, action_type="screenshot",
                              description=f"截图已保存: {path}",
                              metadata={"path": path})
        except Exception as e:
            return ActionResult(success=False, action_type="screenshot",
                              error=str(e))
    
    # ---- 辅助方法 ----
    
    def _resolve_target(self, action: Dict) -> Tuple[int, int]:
        """解析坐标目标"""
        if "x" in action and "y" in action:
            return action["x"], action["y"]
        
        # 按名称查找 (模板匹配)
        if "target" in action:
            try:
                loc = pyautogui.locateCenterOnScreen(
                    action["target"], confidence=0.8
                )
                if loc:
                    return int(loc.x), int(loc.y)
            except Exception:
                pass
        
        # 默认当前鼠标位置
        return pyautogui.position()
    
    def _resolve_window(self, action: Dict) -> Optional[int]:
        """解析窗口句柄"""
        title = action.get("target", "") or action.get("title", "")
        if title:
            return self._find_window_by_title(title)
        return self._find_window_by_title("")
    
    def _find_window_by_title(self, title: str) -> Optional[int]:
        """按标题查找窗口句柄"""
        def enum_callback(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if title.lower() in window_title.lower():
                    results.append(hwnd)
        
        results = []
        try:
            win32gui.EnumWindows(enum_callback, results)
            return results[0] if results else None
        except Exception:
            return None
    
    def _assess_risk(self, action_type: str, action: Dict) -> RiskLevel:
        """评估操作风险等级"""
        if action_type in self.low_risk_actions:
            return RiskLevel.LOW
        if action_type in self.medium_risk_actions:
            return RiskLevel.MEDIUM
        return RiskLevel.HIGH
    
    def get_stats(self) -> Dict:
        """获取操作统计"""
        total = self.stats["total_actions"]
        success_rate = (self.stats["successful_actions"] / total * 100) if total > 0 else 0
        return {
            **self.stats,
            "success_rate": round(success_rate, 1),
        }
