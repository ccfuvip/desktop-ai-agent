"""
桌面感知引擎 (Desktop Awareness Engine)
======================================
实时感知整个Windows桌面：窗口、控件、鼠标、截图

技术栈:
- UIA控件树: uiautomation (毫秒级)
- 屏幕捕获: mss (高速)
- 窗口枚举: pywin32 (win32gui/win32con)
- 鼠标追踪: pyautogui

作者: Desktop AI Agent
版本: 1.0.0
"""

import time
import threading
import json
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field, asdict
from pathlib import Path

import mss
import pyautogui
import uiautomation as auto
from PIL import Image
import io

# ---- 必须在文件顶部导入 ----
import win32gui
import win32con
import win32api


@dataclass
class WindowInfo:
    """窗口信息"""
    title: str = ""
    class_name: str = ""
    hwnd: int = 0
    process_name: str = ""
    pid: int = 0
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    is_visible: bool = True
    is_minimized: bool = False
    is_maximized: bool = False
    is_foreground: bool = False
    opacity: int = 255


@dataclass
class ControlInfo:
    """UIA控件信息"""
    name: str = ""
    control_type: str = ""
    automation_id: str = ""
    rect: Tuple[int, int, int, int] = (0, 0, 0, 0)
    is_enabled: bool = True
    is_keyboard_focusable: bool = False
    value: str = ""
    parent_name: str = ""


@dataclass
class DesktopState:
    """完整桌面状态快照"""
    timestamp: float = 0.0
    mouse_position: Tuple[int, int] = (0, 0)
    active_window: Optional[WindowInfo] = None
    all_windows: List[WindowInfo] = field(default_factory=list)
    foreground_controls: List[ControlInfo] = field(default_factory=list)
    screenshot: Optional[bytes] = None  # base64 encoded
    total_windows: int = 0
    uptime_seconds: float = 0.0


class DesktopAwarenessEngine:
    """
    桌面感知引擎
    
    三层感知架构:
    1. UIA控件树 (毫秒级) - 读取Windows Accessibility Tree
    2. 窗口枚举 (百毫秒级) - 获取所有窗口状态
    3. 屏幕捕获 (秒级) - 高分辨率截图用于视觉模型
    
    使用示例:
        engine = DesktopAwarenessEngine()
        state = engine.quick_scan()
        controls = engine.get_control_tree()
        screenshot = engine.capture_screen()
    """
    
    def __init__(self, capture_fps: int = 5, resolution: str = "720p"):
        self.capture_fps = capture_fps
        self.resolution = resolution
        
        # 屏幕捕获区域
        self.sct_mgr = mss.mss()
        self._screen_rect = self._get_capture_rect()
        
        # 性能指标
        self.stats = {
            "last_scan_time_ms": 0,
            "total_scans": 0,
            "errors": 0,
            "uptime": 0,
        }
        self._start_time = time.time()
        
        # 后台监控
        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._last_state: Optional[DesktopState] = None
        self._state_change_callback = None
        
        # 初始化pyautogui安全设置
        pyautogui.FAILSAFE = True  # 鼠标移到左上角可紧急停止
    
    def _get_capture_rect(self) -> dict:
        """获取捕获区域"""
        monitors = self.sct_mgr.monitors
        if len(monitors) < 1:
            return {"left": 0, "top": 0, "width": 1920, "height": 1080}
        
        # mss v10+ 返回字典格式
        # monitors[0] 通常是虚拟屏幕(全0表示无效)，monitors[1] 是主显示器
        if len(monitors) > 1 and monitors[0].get("width", 0) == 0:
            monitor = monitors[1]
        else:
            monitor = monitors[0]
        
        mw = monitor.get("width", 1920)
        mh = monitor.get("height", 1080)
        ml = monitor.get("left", 0)
        mt = monitor.get("top", 0)
        
        if self.resolution == "720p":
            w, h = mw // 2, mh // 2
        elif self.resolution == "1080p":
            w, h = mw, mh
        else:
            w, h = mw, mh
        
        return {
            "left": ml + (mw - w) // 2,
            "top": mt + (mh - h) // 2,
            "width": w,
            "height": h,
        }
    
    def quick_scan(self) -> dict:
        """
        快速扫描桌面状态
        
        返回简化的桌面状态字典，适合频繁调用。
        耗时: ~50-200ms
        """
        start = time.time()
        
        try:
            # 获取鼠标位置
            mx, my = pyautogui.position()
            
            # 获取活跃窗口
            active_hwnd = auto.GetForegroundControl()
            active_window = self._get_window_info(active_hwnd) if active_hwnd else None
            
            # 获取所有窗口
            windows = self._enumerate_windows()
            
            elapsed = (time.time() - start) * 1000
            self.stats["last_scan_time_ms"] = elapsed
            self.stats["total_scans"] += 1
            
            return {
                "timestamp": time.time(),
                "mouse_position": (mx, my),
                "active_window": self._window_to_dict(active_window) if active_window else None,
                "window_list": [self._window_to_dict(w) for w in windows[:20]],
                "total_windows": len(windows),
                "scan_time_ms": round(elapsed, 1),
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            return {
                "timestamp": time.time(),
                "mouse_position": pyautogui.position(),
                "error": str(e),
                "total_windows": 0,
            }
    
    def get_full_state(self) -> DesktopState:
        """
        获取完整桌面状态
        
        包含截图和控制树，适合需要深度感知的场景。
        耗时: ~500-1500ms
        """
        start = time.time()
        
        state = DesktopState(
            timestamp=time.time(),
            mouse_position=pyautogui.position(),
            uptime_seconds=time.time() - self._start_time,
        )
        
        try:
            # 活跃窗口
            active_hwnd = auto.GetForegroundControl()
            if active_hwnd:
                state.active_window = self._get_window_info(active_hwnd)
            
            # 所有窗口
            state.all_windows = self._enumerate_windows()
            state.total_windows = len(state.all_windows)
            
            # 前台控件树
            if state.active_window:
                state.foreground_controls = self._get_control_tree(
                    state.active_window.hwnd
                )
            
            # 截图
            state.screenshot = self.capture_screen_region()
            
            elapsed = (time.time() - start) * 1000
            self.stats["last_scan_time_ms"] = elapsed
            
        except Exception as e:
            self.stats["errors"] += 1
            state.error = str(e)
        
        self._last_state = state
        return state
    
    def get_control_tree(self, hwnd: int = None) -> List[ControlInfo]:
        """
        获取UIA控件树
        
        Args:
            hwnd: 窗口句柄，None表示当前前台窗口
            
        Returns:
            控件列表，包含名称、类型、位置等信息
        """
        controls = []
        
        try:
            if hwnd:
                root = auto.Control(controlId=hwnd)
            else:
                root = auto.GetForegroundControl()
            
            if not root:
                return controls
            
            self._walk_controls(root, controls, "")
            
        except Exception:
            pass
        
        return controls
    
    def capture_screen(self) -> bytes:
        """
        截取全屏
        
        Returns:
            PNG格式的截图字节数据
        """
        return self.capture_screen_region()
    
    def capture_screen_region(self, rect: Optional[Tuple[int, int, int, int]] = None) -> bytes:
        """
        截取指定区域或全屏
        
        Args:
            rect: (left, top, width, height)，None表示全屏
            
        Returns:
            PNG格式的截图字节数据
        """
        try:
            if rect:
                sct = self.sct_mgr.grab(rect)
            else:
                sct = self.sct_mgr.grab(self._screen_rect)
            
            img = Image.frombytes("RGB", sct.size, sct.bgra, "raw", "BGRX")
            
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        
        except Exception:
            return b""
    
    def capture_active_window(self) -> bytes:
        """截取当前活跃窗口"""
        try:
            hwnd = auto.GetForegroundControl()
            if not hwnd:
                return self.capture_screen()
            
            rect = self._get_window_rect(hwnd)
            if rect:
                return self.capture_screen_region(rect)
            return self.capture_screen()
        
        except Exception:
            return self.capture_screen()
    
    def start_realtime_monitoring(self, callback=None, interval_ms: int = 500):
        """
        启动实时监控
        
        Args:
            callback: 状态变化时的回调函数 callback(new_state, old_state)
            interval_ms: 检查间隔(毫秒)
        """
        if self._monitoring:
            return
        
        self._state_change_callback = callback
        self._monitoring = True
        
        def monitor_loop():
            while self._monitoring:
                try:
                    new_state = self.quick_scan()
                    if self._last_state:
                        if self._has_changed(new_state, self._last_state):
                            if callback:
                                callback(new_state, self._last_state)
                    self._last_state = new_state
                except Exception:
                    pass
                
                time.sleep(interval_ms / 1000.0)
        
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_realtime_monitoring(self):
        """停止实时监控"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
    
    # ---- 私有方法 ----
    
    def _enumerate_windows(self) -> List[WindowInfo]:
        """枚举所有可见窗口"""
        windows = []
        
        def enum_callback(hwnd, _):
            if hwnd == 0:
                return True
            
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return True
                
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return True
                
                class_name = win32gui.GetClassName(hwnd)
                _, pid = win32gui.GetWindowThreadProcessId(hwnd)
                
                rect = win32gui.GetWindowRect(hwnd)
                
                is_foreground = win32gui.GetForegroundWindow() == hwnd
                
                try:
                    style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                    is_minimized = bool(style & win32con.WS_MINIMIZE)
                    is_maximized = bool(style & win32con.WS_MAXIMIZE)
                except Exception:
                    is_minimized = False
                    is_maximized = False
                
                win = WindowInfo(
                    title=title,
                    class_name=class_name,
                    hwnd=hwnd,
                    pid=pid,
                    rect=rect,
                    is_visible=True,
                    is_minimized=is_minimized,
                    is_maximized=is_maximized,
                    is_foreground=is_foreground,
                )
                
                # 获取进程名
                try:
                    import psutil
                    proc = psutil.Process(pid)
                    win.process_name = proc.name()
                except Exception:
                    pass
                
                windows.append(win)
            
            except Exception:
                pass
            
            return True
        
        try:
            win32gui.EnumWindows(enum_callback, None)
        except Exception:
            # 降级：使用uiautomation
            try:
                root = auto.RootControl()
                for child in root.GetChildren():
                    try:
                        rect = child.BoundingRectangle
                        windows.append(WindowInfo(
                            title=child.Name,
                            class_name=child.ControlTypeName,
                            hwnd=child.NativeWindowHandle,
                            rect=(rect.left, rect.top, rect.width, rect.height),
                        ))
                    except Exception:
                        pass
            except Exception:
                pass
        
        return windows
    
    def _get_window_info(self, hwnd) -> Optional[WindowInfo]:
        """获取单个窗口信息"""
        try:
            if hasattr(hwnd, 'BoundingRectangle'):
                rect = hwnd.BoundingRectangle
                return WindowInfo(
                    title=hwnd.Name,
                    class_name=hwnd.ControlTypeName,
                    hwnd=hwnd.NativeWindowHandle,
                    rect=(rect.left, rect.top, rect.width, rect.height),
                )
            return None
        except Exception:
            return None
    
    def _get_window_rect(self, hwnd) -> Optional[Tuple[int, int, int, int]]:
        """获取窗口rect用于截图"""
        try:
            if hasattr(hwnd, 'BoundingRectangle'):
                r = hwnd.BoundingRectangle
                return (r.left, r.top, r.right - r.left, r.bottom - r.top)
            return None
        except Exception:
            return None
    
    def _walk_controls(self, control, controls: List[ControlInfo], parent_name: str, depth: int = 0):
        """递归遍历UIA控件树"""
        if depth > 5:  # 限制深度防止卡死
            return
        
        try:
            rect = control.BoundingRectangle
            controls.append(ControlInfo(
                name=control.Name,
                control_type=control.ControlTypeName,
                automation_id=control.AutomationId,
                rect=(rect.left, rect.top, rect.width, rect.height),
                is_enabled=control.IsEnabled,
                is_keyboard_focusable=control.IsKeyboardFocusable,
                value=control.ValueValue if hasattr(control, 'ValueValue') else "",
                parent_name=parent_name,
            ))
            
            for child in control.GetChildren():
                self._walk_controls(child, controls, control.Name, depth + 1)
        
        except Exception:
            pass
    
    def _window_to_dict(self, w: WindowInfo) -> dict:
        """窗口信息转字典"""
        d = asdict(w)
        d["rect"] = list(d["rect"])
        return d
    
    def _has_changed(self, new: dict, old: dict) -> bool:
        """检测桌面状态是否变化"""
        try:
            if new.get("active_window", {}).get("title") != old.get("active_window", {}).get("title"):
                return True
            if new.get("mouse_position") != old.get("mouse_position"):
                return True
            if new.get("total_windows") != old.get("total_windows"):
                return True
        except Exception:
            pass
        return False
