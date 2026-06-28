"""
主界面 (Main UI) — PyQt6桌面应用
负责：用户交互、聊天面板、桌面预览、进化仪表盘

界面布局：
┌─────────────────────────────────────────────────────────────┐
│  [Logo] 桌面AI Agent v3.0              [设置] [最小化] [关闭] │
├──────────┬────────────────────────────────┬─────────────────┤
│          │                                │  📊 进化仪表盘   │
│  导航栏   │        聊天面板                 │                 │
│          │                                │  知识: 1247     │
│  🏠 主页  │  [用户消息气泡]                 │  技能: 23       │
│  💬 聊天  │  [Agent回复 + 操作结果]         │  插件: 8        │
│  🖥️ 桌面  │                                │  模型: 6        │
│  🔧 工具  │                                │                 │
│  📈 进化  │                                │  ┌──────────┐  │
│  ⚙️ 设置  │                                │  │性能趋势图│  │
│          │                                │  └──────────┘  │
│          │                                │                 │
├──────────┴────────────────────────────────┴─────────────────┤
│  🟢 就绪  |  GPU: 12/16GB  |  CPU: 25%  |  记忆: 1247条     │
└─────────────────────────────────────────────────────────────┘
"""
import sys
import threading
import json
import time
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
import httpx

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTextEdit, QPlainTextEdit, QLabel, QPushButton, QLineEdit,
        QSplitter, QFrame, QScrollArea, QTabWidget, QGroupBox,
        QProgressBar, QComboBox, QToolBar, QStatusBar, QMenu,
        QMessageBox, QSizePolicy, QGridLayout, QSpinBox, QCheckBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
        QDialog, QFormLayout, QListWidget, QListWidgetItem,
    )
    from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve
    from PyQt6.QtGui import QFont, QIcon, QColor, QPainter, QPen, QBrush, QPixmap
except ImportError:
    print("PyQt6 not installed. Run: pip install PyQt6")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 颜色主题
# ---------------------------------------------------------------------------

DARK_THEME = {
    "bg_primary": "#1e1e2e",
    "bg_secondary": "#181825",
    "bg_tertiary": "#11111b",
    "bg_hover": "#313244",
    "bg_active": "#45475a",
    "text_primary": "#cdd6f4",
    "text_secondary": "#a6adc8",
    "text-secondary": "#a6adc8",
    "text-muted": "#6c7086",
    "accent": "#89b4fa",
    "accent-hover": "#74c7ec",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "yellow": "#f9e2af",
    "blue": "#89b4fa",
    "purple": "#cba6f7",
    "orange": "#fab387",
    "border": "#313244",
}


# ---------------------------------------------------------------------------
# 进化仪表盘组件
# ---------------------------------------------------------------------------

class EvolutionDashboard(QWidget):
    """进化仪表盘 — 显示Agent的成长状态"""
    
    def __init__(self, optimization_engine=None, learning_engine=None,
                 upgrade_engine=None, collaboration_engine=None, parent=None):
        super().__init__(parent)
        self.opt_engine = optimization_engine
        self.learn_engine = learning_engine
        self.upgrade_engine = upgrade_engine
        self.collab_engine = collaboration_engine
        
        self._setup_ui()
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self.refresh)
        self._update_timer.start(5000)  # 每5秒刷新
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("🧬 进化仪表盘")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {DARK_THEME['purple']}; padding: 5px;")
        layout.addWidget(title)
        
        # 概览卡片区域
        cards_layout = QGridLayout()
        cards_layout.setSpacing(8)
        
        # 知识卡片
        self.knowledge_card = self._create_stat_card("📚 知识库", "0", DARK_THEME['blue'])
        cards_layout.addWidget(self.knowledge_card, 0, 0)
        
        # 技能卡片
        self.skill_card = self._create_stat_card("🛠️ 技能", "0", DARK_THEME['green'])
        cards_layout.addWidget(self.skill_card, 0, 1)
        
        # 插件卡片
        self.plugin_card = self._create_stat_card("🔌 插件", "0", DARK_THEME['orange'])
        cards_layout.addWidget(self.plugin_card, 0, 2)
        
        # 模型卡片
        self.model_card = self._create_stat_card("🤖 模型", "0", DARK_THEME['purple'])
        cards_layout.addWidget(self.model_card, 0, 3)
        
        layout.addLayout(cards_layout)
        
        # 分隔线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"color: {DARK_THEME['border']};")
        layout.addWidget(separator)
        
        # 性能监控区域
        perf_group = QGroupBox("📊 性能监控")
        perf_layout = QVBoxLayout(perf_group)
        
        # GPU显存
        gpu_label = QLabel("GPU 显存使用:")
        perf_layout.addWidget(gpu_label)
        self.gpu_progress = QProgressBar()
        self.gpu_progress.setMaximumHeight(20)
        self.gpu_progress.setStyleSheet(self._progress_style(DARK_THEME['blue']))
        perf_layout.addWidget(self.gpu_progress)
        
        # CPU使用
        cpu_label = QLabel("CPU 使用:")
        perf_layout.addWidget(cpu_label)
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setMaximumHeight(20)
        self.cpu_progress.setStyleSheet(self._progress_style(DARK_THEME['green']))
        perf_layout.addWidget(self.cpu_progress)
        
        # 内存使用
        mem_label = QLabel("内存使用:")
        perf_layout.addWidget(mem_label)
        self.mem_progress = QProgressBar()
        self.mem_progress.setMaximumHeight(20)
        self.mem_progress.setStyleSheet(self._progress_style(DARK_THEME['yellow']))
        perf_layout.addWidget(self.mem_progress)
        
        layout.addWidget(perf_group)
        
        # 分隔线
        separator2 = QFrame()
        separator2.setFrameShape(QFrame.Shape.HLine)
        separator2.setFrameShadow(QFrame.Shadow.Sunken)
        separator2.setStyleSheet(f"color: {DARK_THEME['border']};")
        layout.addWidget(separator2)
        
        # 任务统计
        task_group = QGroupBox("📋 任务统计")
        task_layout = QFormLayout(task_group)
        
        self.total_tasks_label = QLabel("0")
        self.success_rate_label = QLabel("0%")
        self.avg_duration_label = QLabel("0s")
        
        task_layout.addRow("总任务数:", self.total_tasks_label)
        task_layout.addRow("成功率:", self.success_rate_label)
        task_layout.addRow("平均耗时:", self.avg_duration_label)
        
        layout.addWidget(task_group)
        
        # 分隔线
        separator3 = QFrame()
        separator3.setFrameShape(QFrame.Shape.HLine)
        separator3.setFrameShadow(QFrame.Shadow.Sunken)
        separator3.setStyleSheet(f"color: {DARK_THEME['border']};")
        layout.addWidget(separator3)
        
        # 最近活动
        activity_group = QGroupBox("🕐 最近活动")
        activity_layout = QVBoxLayout(activity_group)
        
        self.activity_list = QListWidget()
        self.activity_list.setMaximumHeight(120)
        self.activity_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DARK_THEME['bg_secondary']};
                color: {DARK_THEME['text_primary']};
                border: 1px solid {DARK_THEME['border']};
                border-radius: 5px;
                padding: 5px;
            }}
            QListWidget::item {{
                padding: 3px;
            }}
            QListWidget::item:selected {{
                background-color: {DARK_THEME['bg_active']};
            }}
        """)
        activity_layout.addWidget(self.activity_list)
        
        layout.addWidget(activity_group)
        
        layout.addStretch()
    
    def _create_stat_card(self, title: str, value: str, color: str) -> QFrame:
        """创建统计卡片"""
        card = QFrame()
        card.setFixedHeight(70)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_THEME['bg_secondary']};
                border: 1px solid {DARK_THEME['border']};
                border-radius: 8px;
                padding: 8px;
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        
        label = QLabel(title)
        label.setFont(QFont("Microsoft YaHei", 9))
        label.setStyleSheet(f"color: {DARK_THEME['text_secondary']};")
        card_layout.addWidget(label)
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        value_label.setStyleSheet(f"color: {color};")
        card_layout.addWidget(value_label)
        
        return card
    
    def _progress_style(self, color: str) -> str:
        """进度条样式"""
        return f"""
            QProgressBar {{
                background-color: {DARK_THEME['bg_tertiary']};
                border: 1px solid {DARK_THEME['border']};
                border-radius: 5px;
                text-align: center;
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """
    
    def refresh(self):
        """刷新仪表盘数据"""
        try:
            import psutil
            
            # 更新性能监控
            cpu_pct = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            
            self.cpu_progress.setValue(int(cpu_pct))
            self.mem_progress.setValue(int(mem.percent))
            
            # GPU显存
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    used, total = map(float, result.stdout.strip().split(","))
                    gpu_pct = int(used / total * 100)
                    self.gpu_progress.setValue(gpu_pct)
                    self.gpu_progress.setFormat(f"{used/1024:.1f}/{total/1024:.1f} GB")
                else:
                    self.gpu_progress.setFormat("N/A")
            except Exception:
                self.gpu_progress.setFormat("N/A")
            
            # 更新统计
            if self.learn_engine:
                stats = self.learn_engine.get_stats()
                self.knowledge_card.findChildren(QLabel)[-1].setText(str(stats.get("knowledge_items", 0)))
                self.skill_card.findChildren(QLabel)[-1].setText(str(stats.get("skills_learned", 0)))
                self.plugin_card.findChildren(QLabel)[-1].setText(str(stats.get("plugins_discovered", 0)))
            
            if self.upgrade_engine:
                model_stats = self.upgrade_engine.get_stats()
                self.model_card.findChildren(QLabel)[-1].setText(str(model_stats.get("total_models", 0)))
            
            if self.opt_engine:
                dashboard = self.opt_engine.get_dashboard_data()
                self.total_tasks_label.setText(str(dashboard.get("total_tasks", 0)))
                self.success_rate_label.setText(f"{dashboard.get('success_rate', 0)*100:.0f}%")
                self.avg_duration_label.setText(f"{dashboard.get('avg_duration_sec', 0):.1f}s")
            
            # 更新最近活动
            if self.opt_engine:
                recent = self.opt_engine._reflection_log[-5:] if hasattr(self.opt_engine, '_reflection_log') else []
                self.activity_list.clear()
                for r in reversed(recent):
                    desc = r.get("analysis", {}).get("speed", "unknown")
                    self.activity_list.addItem(f"🔄 {desc}: {r.get('description', '')[:30]}")
        
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 聊天面板组件
# ---------------------------------------------------------------------------

class ChatPanel(QFrame):
    """聊天面板 — 显示用户和Agent的对话"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("chatPanel")
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # 聊天消息区域（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)
        
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_layout.setSpacing(8)
        self.chat_layout.setContentsMargins(5, 5, 5, 5)
        
        scroll.setWidget(self.chat_container)
        layout.addWidget(scroll)
        
        # 输入区域
        input_layout = QHBoxLayout()
        
        self.message_input = QPlainTextEdit()
        self.message_input.setPlaceholderText("输入指令... (Ctrl+Enter发送)")
        self.message_input.setMaximumHeight(60)
        self.message_input.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DARK_THEME['bg_secondary']};
                color: {DARK_THEME['text_primary']};
                border: 1px solid {DARK_THEME['border']};
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }}
            QPlainTextEdit:focus {{
                border: 1px solid {DARK_THEME['accent']};
            }}
        """)
        input_layout.addWidget(self.message_input, 1)
        
        send_btn = QPushButton("发送")
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK_THEME['accent']};
                color: {DARK_THEME['bg_tertiary']};
                border: none;
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {DARK_THEME['accent-hover']};
            }}
            QPushButton:pressed {{
                background-color: {DARK_THEME['blue']};
            }}
        """)
        send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(send_btn)
        
        layout.addLayout(input_layout)
    
    def _send_message(self):
        """发送消息 -> 转发到本机 start_remote API (端口9999)"""
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        # 添加用户消息
        self._add_message(text, "user")
        self.message_input.setPlainText("")

        # 占位提示
        placeholder = self._add_message("⏳ 正在调用 Agent ...", "agent")

        def _do_call():
            try:
                resp = httpx.post(
                    "http://127.0.0.1:9999/api/command",
                    json={
                        "command": "agent_chat",
                        "params": {"message": text},
                        "source": "ui",
                        "priority": 5,
                    },
                    timeout=120.0,
                )
                data = resp.json()
                if data.get("success"):
                    content = data.get("response", "(无内容)")
                else:
                    errs = data.get("errors", [])
                    content = f"❌ 失败: {errs[0] if errs else data.get('response', '未知错误')}"
                steps = data.get("steps", 0)
                if steps:
                    content = f"{content}\n\n[步骤: {steps}]"
            except Exception as e:
                content = f"❌ 网络错误: {e}"

            # 替换占位气泡
            QTimer.singleShot(0, lambda: self._replace_last_agent(placeholder, content))

        threading.Thread(target=_do_call, daemon=True).start()

    def _replace_last_agent(self, old_frame, new_text):
        """把最后一条 agent 消息替换成 new_text"""
        try:
            idx = self.chat_layout.indexOf(old_frame)
            if idx >= 0:
                # 找到里面的 bubble (第二个 widget)
                bubble = old_frame.layout().itemAt(1).widget() if old_frame.layout().count() > 1 else None
                if bubble is not None:
                    bubble.setText(new_text)
                    return
        except Exception:
            pass
        # 兜底: 直接追加
        self._add_message(new_text, "agent")
    
    def _add_message(self, text: str, sender: str):
        """添加一条消息到聊天面板"""
        msg_frame = QFrame()
        msg_layout = QHBoxLayout(msg_frame)
        msg_layout.setContentsMargins(5, 3, 5, 3)
        
        if sender == "user":
            # 用户消息 — 右对齐
            msg_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
            bubble = QLabel(text)
            bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {DARK_THEME['accent']};
                    color: {DARK_THEME['bg_tertiary']};
                    border-radius: 12px;
                    padding: 8px 12px;
                    font-size: 13px;
                    max-width: 500px;
                }}
            """)
            msg_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignRight)
        else:
            # Agent消息 — 左对齐
            avatar = QLabel("🤖")
            avatar.setFixedSize(24, 24)
            msg_layout.addWidget(avatar)
            
            bubble = QLabel(text)
            bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {DARK_THEME['bg_secondary']};
                    color: {DARK_THEME['text_primary']};
                    border-radius: 12px;
                    padding: 8px 12px;
                    font-size: 13px;
                    max-width: 500px;
                }}
            """)
            msg_layout.addWidget(bubble, 0, Qt.AlignmentFlag.AlignLeft)
        
        self.chat_layout.addWidget(msg_frame)
        
        # 自动滚动到底部
        self.chat_container.parentWidget().parentWidget().verticalScrollBar().setValue(
            self.chat_container.parentWidget().parentWidget().verticalScrollBar().maximum()
        )


# ---------------------------------------------------------------------------
# 桌面预览面板
# ---------------------------------------------------------------------------

class DesktopPreviewPanel(QFrame):
    """桌面预览面板 — 显示Agent看到的桌面状态"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
        # 定时刷新桌面截图
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_desktop)
        self._refresh_timer.start(2000)  # 每2秒刷新
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        title = QLabel("🖥️ 桌面预览")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {DARK_THEME['text_secondary']}; padding: 3px;")
        layout.addWidget(title)
        
        self.desktop_label = QLabel("等待首次截图...")
        self.desktop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desktop_label.setStyleSheet(f"""
            QLabel {{
                background-color: {DARK_THEME['bg_secondary']};
                border: 2px dashed {DARK_THEME['border']};
                border-radius: 8px;
                color: {DARK_THEME['text-muted']};
                font-size: 12px;
            }}
        """)
        self.desktop_label.setMinimumHeight(200)
        layout.addWidget(self.desktop_label)
        
        # 状态信息
        status_layout = QHBoxLayout()
        
        self.window_label = QLabel("窗口: --")
        self.mouse_label = QLabel("鼠标: --")
        
        status_layout.addWidget(self.window_label)
        status_layout.addStretch()
        status_layout.addWidget(self.mouse_label)
        
        layout.addLayout(status_layout)
    
    def _refresh_desktop(self):
        """刷新桌面预览（简化版，实际需要调用awareness_engine）"""
        try:
            import pyautogui
            pos = pyautogui.position()
            self.mouse_label.setText(f"鼠标: {pos.x}, {pos.y}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """主窗口 — 整个Agent的GUI"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__()
        self.config = config or {}
        self._setup_ui()
        self._apply_theme()
    
    def _setup_ui(self):
        """设置UI布局"""
        self.setWindowTitle("🤖 桌面AI Agent v3.0")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)
        
        # 中心部件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 左侧导航栏
        nav = self._create_navigation()
        main_layout.addWidget(nav)
        
        # 分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 中间区域（聊天面板）
        self.chat = ChatPanel()
        splitter.addWidget(self.chat)
        
        # 右侧区域（进化仪表盘 + 桌面预览）
        right_panel = QStackedWidget()
        
        # 进化仪表盘tab
        self.dashboard = EvolutionDashboard()
        right_panel.addWidget(self.dashboard)
        
        # 桌面预览tab
        self.desktop_preview = DesktopPreviewPanel()
        right_panel.addWidget(self.desktop_preview)
        
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)  # 聊天面板占3份
        splitter.setStretchFactor(1, 1)  # 右侧面板占1份
        
        main_layout.addWidget(splitter)
        
        # 底部状态栏
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: {DARK_THEME['bg_secondary']};
                color: {DARK_THEME['text-secondary']};
                border-top: 1px solid {DARK_THEME['border']};
            }}
        """)
        
        self.status_label = QLabel("🟢 就绪")
        self.gpu_label = QLabel("GPU: --")
        self.mem_label = QLabel("内存: --")
        self.status_bar.addWidget(self.status_label)
        self.status_bar.addPermanentWidget(self.gpu_label)
        self.status_bar.addPermanentWidget(self.mem_label)
        
        # 定时更新状态栏
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status_bar)
        self._status_timer.start(3000)
    
    def _create_navigation(self) -> QFrame:
        """创建左侧导航栏"""
        nav = QFrame()
        nav.setFixedWidth(60)
        nav.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_THEME['bg_secondary']};
                border-right: 1px solid {DARK_THEME['border']};
            }}
        """)
        
        layout = QVBoxLayout(nav)
        layout.setContentsMargins(5, 10, 5, 10)
        layout.setSpacing(8)
        
        # Logo
        logo = QLabel("🤖")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(40, 40)
        logo.setFont(QFont("Segoe UI Emoji", 24))
        layout.addWidget(logo)
        
        layout.addStretch()
        
        # 导航按钮
        nav_items = [
            ("📊", "仪表盘"),
            ("💬", "聊天"),
            ("🖥️", "桌面"),
            ("🔧", "工具"),
            ("⚙️", "设置"),
        ]
        
        for icon, tooltip in nav_items:
            btn = QPushButton(icon)
            btn.setFixedSize(40, 40)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    font-size: 20px;
                }}
                QPushButton:hover {{
                    background-color: {DARK_THEME['bg_hover']};
                }}
                QPushButton:pressed {{
                    background-color: {DARK_THEME['bg_active']};
                }}
            """)
            layout.addWidget(btn)
        
        layout.addStretch()
        
        return nav
    
    def _apply_theme(self):
        """应用深色主题"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {DARK_THEME['bg_primary']};
            }}
            QStatusBar {{
                background-color: {DARK_THEME['bg_secondary']};
                color: {DARK_THEME['text_secondary']};
                font-size: 12px;
            }}
            QToolTip {{
                background-color: {DARK_THEME['bg_tertiary']};
                color: {DARK_THEME['text_primary']};
                border: 1px solid {DARK_THEME['border']};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
    
    def _update_status_bar(self):
        """更新状态栏"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            self.mem_label.setText(f"内存: {mem.percent}%")
            
            # GPU
            try:
                import subprocess
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    used, total = map(float, result.stdout.strip().split(","))
                    self.gpu_label.setText(f"GPU: {used/1024:.1f}/{total/1024:.1f}GB")
            except Exception:
                self.gpu_label.setText("GPU: N/A")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    """启动主程序"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 跨平台一致的外观
    
    # 加载配置
    PROJECT_DIR = Path(__file__).parent.resolve()
    config_path = PROJECT_DIR / "config.yaml"
    config = {}
    if config_path.exists():
        try:
            import yaml
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    
    # 创建主窗口
    window = MainWindow(config)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
