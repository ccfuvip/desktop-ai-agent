"""
远程控制接口 (Remote Control Interface)
=====================================
让其他AI智能体可以通过HTTP/MCP协议操控本Agent

两种模式:
1. 被操控 (Server模式) — 其他AI通过HTTP API指挥本Agent
2. 操控别人 (Client模式) — 本Agent通过MCP/API指挥其他AI

核心接口:
- POST /api/command — 接收远程指令
- GET  /api/status   — 返回Agent状态
- POST /api/controll — 连接并操控其他AI
- WS   /ws/control  — WebSocket实时双向通信

作者: Desktop AI Agent
版本: 1.0.0
"""

import json
import time
import asyncio
import logging
import uuid
import threading
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class RemoteCommand:
    """远程指令"""
    id: str = ""
    source: str = ""          # 谁发的指令 (AI名称/IP)
    command: str = ""         # 指令类型
    params: dict = field(default_factory=dict)
    timestamp: float = 0.0
    priority: int = 1         # 1-10, 10最高
    requires_confirmation: bool = False  # 是否需要确认
    timeout: int = 300         # 超时时间(秒)


@dataclass
class RemoteResponse:
    """远程响应"""
    command_id: str = ""
    success: bool = False
    result: str = ""
    error: str = ""
    duration_ms: float = 0.0
    timestamp: float = 0.0


@dataclass
class ControlledAI:
    """被操控的AI智能体"""
    id: str = ""
    name: str = ""
    type: str = ""  # mcp, http_api, websocket, custom
    endpoint: str = ""
    api_key: str = ""
    capabilities: List[str] = field(default_factory=list)
    status: str = "disconnected"  # connected, busy, idle, error
    last_contact: float = 0.0
    latency_ms: float = 0.0
    success_rate: float = 0.0
    total_commands: int = 0
    successful_commands: int = 0


# ============================================================
# HTTP API 处理器
# ============================================================

class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""
    
    # 通过类变量注入AgentCore引用
    agent_core = None
    perception = None
    controller = None
    memory = None
    optimization = None
    collaboration = None
    
    def log_message(self, format, *args):
        """重写日志格式"""
        logger.debug(f"HTTP: {args[0]}")
    
    def _send_json(self, status_code: int, data: dict):
        """发送JSON响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))
    
    def _read_body(self) -> dict:
        """读取请求体"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
    
    def do_OPTIONS(self):
        """CORS预检请求"""
        self._send_json(200, {"status": "ok"})
    
    def do_GET(self):
        """处理GET请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/status":
            self._handle_status()
        elif path == "/api/ai/list":
            self._handle_ai_list()
        elif path == "/api/health":
            self._handle_health()
        elif path == "/api/performance":
            self._handle_performance()
        elif path == "/":
            self._handle_root()
        else:
            self._send_json(404, {"error": "Not Found", "path": path})
    
    def do_POST(self):
        """处理POST请求"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == "/api/command":
            self._handle_command()
        elif path == "/api/controll":
            self._handle_connect_ai()
        elif path == "/api/execute":
            self._handle_execute()
        elif path == "/api/teammate/assign":
            self._handle_assign_teammate()
        else:
            self._send_json(404, {"error": "Not Found"})
    
    def _handle_root(self):
        """根路径 — API文档"""
        self._send_json(200, {
            "name": "Desktop AI Agent Remote Control API",
            "version": "1.0.0",
            "endpoints": {
                "GET /": "API文档",
                "GET /api/health": "健康检查",
                "GET /api/status": "Agent状态",
                "GET /api/performance": "性能报告",
                "GET /api/ai/list": "已连接的AI列表",
                "POST /api/command": "发送指令给本Agent",
                "POST /api/execute": "执行桌面操作",
                "POST /api/controll": "连接新AI智能体",
                "POST /api/teammate/assign": "分配子任务给AI队友",
            },
            "auth": "如需认证，在Header中添加 X-API-Key",
        })
    
    def _handle_health(self):
        """健康检查"""
        ready = True
        if self.agent_core:
            ready = self.agent_core.status.value != "error"
        
        self._send_json(200, {
            "status": "healthy" if ready else "degraded",
            "ready": ready,
            "timestamp": datetime.now().isoformat(),
        })
    
    def _handle_status(self):
        """Agent状态"""
        status = {"error": "No agent_core"}
        if self.agent_core:
            status = self.agent_core.get_status()
        
        status["remote"] = {
            "api_available": True,
            "connected_ais": self._get_connected_ai_count(),
        }
        
        self._send_json(200, status)
    
    def _handle_performance(self):
        """性能报告"""
        report = {}
        if self.optimization:
            report = self.optimization.get_performance_report()
        self._send_json(200, report)
    
    def _handle_command(self):
        """
        接收远程指令 — 核心接口
        
        其他AI可以通过这个接口指挥本Agent做事
        
        请求格式:
        {
            "command": "open_app",       // 指令类型
            "params": {                  // 参数
                "app_name": "Chrome",
                "action": "launch"
            },
            "priority": 5,               // 优先级 1-10
            "source": "claude_agent"     // 来源标识
        }
        """
        try:
            body = self._read_body()
            
            # API密钥验证（可选）
            api_key = self.headers.get("X-API-Key", "")
            expected_key = body.get("api_key", "")
            if api_key and api_key != expected_key:
                self._send_json(403, {"error": "Invalid API Key"})
                return
            
            command = body.get("command", "")
            params = body.get("params", {})
            priority = body.get("priority", 5)
            source = body.get("source", "unknown")
            
            if not command:
                self._send_json(400, {"error": "Missing command field"})
                return
            
            # 执行指令
            result = self._dispatch_command(command, params, source, priority)
            
            self._send_json(200, result)
        
        except Exception as e:
            logger.exception("远程指令执行失败")
            self._send_json(500, {"error": str(e)})
    
    def _handle_execute(self):
        """
        执行桌面操作 — 简化接口
        
        直接发送桌面操作指令，不需要知道Agent内部结构
        
        请求格式:
        {
            "action": "click",
            "x": 100,
            "y": 200
        }
        """
        try:
            body = self._read_body()
            action = body.get("action", body.get("type", ""))
            params = {k: v for k, v in body.items() if k not in ("action", "type", "api_key")}
            params["type"] = action
            
            if not self.controller:
                self._send_json(503, {"error": "Controller not available"})
                return
            
            result = self.controller.perform_action(params)
            self._send_json(200, result)
        
        except Exception as e:
            self._send_json(500, {"error": str(e)})
    
    def _handle_connect_ai(self):
        """连接一个新的AI智能体"""
        try:
            body = self._read_body()
            name = body.get("name", "")
            ai_type = body.get("type", "http")
            endpoint = body.get("endpoint", "")
            api_key = body.get("api_key", "")
            capabilities = body.get("capabilities", [])
            
            if not name or not endpoint:
                self._send_json(400, {"error": "name and endpoint required"})
                return
            
            # 创建受控AI记录
            ai = ControlledAI(
                id=str(uuid.uuid4())[:8],
                name=name,
                type=ai_type,
                endpoint=endpoint,
                api_key=api_key,
                capabilities=capabilities,
                status="connected",
                last_contact=time.time(),
            )
            
            if self.collaboration and not hasattr(self.collaboration, "_mcp_servers"):
                # 兼容老代码: 旧版本没有 _mcp_servers
                try:
                    self.collaboration._mcp_servers = {}
                except Exception:
                    pass
            if self.collaboration:
                self.collaboration._mcp_servers[name] = {
                    "id": ai.id, "name": ai.name, "type": ai.type,
                    "endpoint": ai.endpoint, "status": ai.status,
                    "last_contact": ai.last_contact, "capabilities": ai.capabilities,
                }
            
            self._send_json(200, {
                "success": True,
                "message": f"AI '{name}' 已连接",
                "ai_id": ai.id,
            })
        
        except Exception as e:
            self._send_json(500, {"error": str(e)})
    
    def _handle_ai_list(self):
        """列出已连接的AI"""
        ais = []
        servers = getattr(self.collaboration, "_mcp_servers", None) if self.collaboration else None
        if servers:
            for name, cfg in servers.items():
                if isinstance(cfg, dict):
                    ais.append({"name": name, "status": cfg.get("status", "unknown")})
                else:
                    ais.append({"name": name, "status": getattr(cfg, "status", "unknown")})
        self._send_json(200, {"ais": ais})
    
    def _handle_assign_teammate(self):
        """
        分配子任务给AI队友
        
        当你需要另一个AI帮忙时，通过这个接口发指令
        
        请求格式:
        {
            "ai_name": "claude",
            "task": "帮我搜索最新的AI论文",
            "timeout": 60
        }
        """
        try:
            body = self._read_body()
            ai_name = body.get("ai_name", "")
            task = body.get("task", "")
            timeout = body.get("timeout", 60)
            
            if not ai_name or not task:
                self._send_json(400, {"error": "ai_name and task required"})
                return
            
            # 通过collaboration引擎分派
            if self.collaboration:
                result = self.collaboration.dispatch_task(ai_name, task, timeout)
                self._send_json(200, {
                    "success": True,
                    "assigned_to": ai_name,
                    "task": task,
                    "result": result,
                })
            else:
                self._send_json(503, {"error": "Collaboration engine not available"})
        
        except Exception as e:
            self._send_json(500, {"error": str(e)})
    
    # ---- 内部方法 ----
    
    def _dispatch_command(self, command: str, params: dict, source: str, priority: int) -> dict:
        """分发指令到对应的处理器"""
        handlers = {
            "desktop_status": self._cmd_desktop_status,
            "take_screenshot": self._cmd_take_screenshot,
            "click": self._cmd_click,
            "type_text": self._cmd_type_text,
            "focus_window": self._cmd_focus_window,
            "open_app": self._cmd_open_app,
            "agent_chat": self._cmd_agent_chat,
            "get_performance": self._cmd_get_performance,
            "list_windows": self._cmd_list_windows,
        }
        
        handler = handlers.get(command)
        if handler:
            try:
                return handler(params, source, priority)
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # 未知指令，尝试作为通用任务发送给AgentCore
        if self.agent_core:
            return self._cmd_general_task(command, params, source, priority)
        
        return {"success": False, "error": f"未知指令: {command}"}
    
    def _cmd_desktop_status(self, params, source, priority):
        if self.perception:
            return self._safe_quick_scan()
        return {"success": False, "error": "Perception engine not available"}

    def _safe_quick_scan(self) -> dict:
        """调用 awareness.quick_scan, 必要时初始化 Windows COM"""
        import pythoncom
        coinit = False
        try:
            try:
                pythoncom.CoInitialize()
                coinit = True
            except pythoncom.com_error:
                pass
            state = self.perception.quick_scan()
            return {"success": True, "data": state}
        except Exception as e:
            return {"success": False, "error": f"quick_scan failed: {e}"}
        finally:
            if coinit:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
    
    def _cmd_take_screenshot(self, params, source, priority):
        if self.perception:
            from datetime import datetime
            import base64
            from pathlib import Path
            from project_paths import PROJECT_DIR
            try:
                img = self.perception.capture_screen()
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = params.get("filename") or f"screenshot_{ts}.png"
                if not Path(filename).is_absolute():
                    filename = str(PROJECT_DIR / "data" / "screenshots" / filename)
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
                Path(filename).write_bytes(img)
                return {
                    "success": True,
                    "file_path": filename,
                    "size_bytes": len(img),
                    "include_base64": params.get("include_base64", False),
                    "image_base64": base64.b64encode(img).decode() if params.get("include_base64") else None,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "error": "Perception engine not available"}
    
    def _cmd_click(self, params, source, priority):
        if self.controller:
            return self.controller.perform_action({
                "type": "click",
                "x": params.get("x"),
                "y": params.get("y"),
            })
        return {"success": False, "error": "Controller not available"}
    
    def _cmd_type_text(self, params, source, priority):
        if self.controller:
            return self.controller.perform_action({
                "type": "type_text",
                "text": params.get("text", ""),
                "speed": params.get("speed", 0.02),
            })
        return {"success": False, "error": "Controller not available"}
    
    def _cmd_focus_window(self, params, source, priority):
        if self.controller:
            return self.controller.perform_action({
                "type": "focus_window",
                "target": params.get("title", ""),
            })
        return {"success": False, "error": "Controller not available"}
    
    def _cmd_open_app(self, params, source, priority):
        import subprocess
        app = params.get("app", "")
        try:
            subprocess.Popen(app, shell=True)
            return {"success": True, "message": f"已启动: {app}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _cmd_agent_chat(self, params, source, priority):
        """通过AgentCore执行自然语言任务"""
        if self.agent_core:
            task = params.get("message", "")
            result = self.agent_core.execute_task(task)
            return {
                "success": result.success,
                "response": result.final_response,
                "steps": result.steps_taken,
                "errors": result.errors,
            }
        return {"success": False, "error": "AgentCore not available"}
    
    def _cmd_get_performance(self, params, source, priority):
        if self.optimization:
            return self.optimization.get_performance_report()
        return {"success": False, "error": "Optimization engine not available"}
    
    def _cmd_list_windows(self, params, source, priority):
        if self.perception:
            result = self._safe_quick_scan()
            if result.get("success"):
                data = result["data"]
                return {"success": True, "windows": data.get("window_list", []), "total": data.get("total_windows", 0)}
            return result
        return {"success": False, "error": "Perception engine not available"}
    
    def _cmd_general_task(self, command, params, source, priority):
        """通用任务 — 将指令转为自然语言发给AgentCore"""
        if self.agent_core:
            message = f"[远程指令来自 {source}] {command}"
            if params:
                message += f" 参数: {json.dumps(params, ensure_ascii=False)}"
            result = self.agent_core.execute_task(message)
            return {
                "success": result.success,
                "response": result.final_response,
                "task_id": result.task_id,
            }
        return {"success": False, "error": "AgentCore not available"}
    
    def _get_connected_ai_count(self) -> int:
        if self.collaboration:
            return len(self.collaboration._mcp_servers)
        return 0


# ============================================================
# 操控其他AI的智能体 (Client Mode)
# ============================================================

class AIClient:
    """
    AI智能体客户端
    
    本Agent可以操控的其他AI智能体。
    支持多种协议: HTTP API, MCP, WebSocket, 自定义
    
    使用示例:
        client = AIClient(
            name="Claude",
            type="http_api",
            endpoint="http://localhost:11434",
            api_key="xxx",
        )
        result = client.execute("搜索最新的AI新闻")
    """
    
    def __init__(self, name: str, ai_type: str, endpoint: str,
                 api_key: str = "", capabilities: List[str] = None):
        self.name = name
        self.ai_type = ai_type
        self.endpoint = endpoint
        self.api_key = api_key
        self.capabilities = capabilities or []
        self.status = "disconnected"
        self.last_contact = 0.0
        self.latency_ms = 0.0
        self.command_count = 0
        self.success_count = 0
    
    async def connect(self) -> bool:
        """连接到AI智能体"""
        start = time.time()
        try:
            if self.ai_type == "http_api":
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(f"{self.endpoint}/health")
                    if resp.status_code == 200:
                        self.status = "connected"
                        self.last_contact = time.time()
                        self.latency_ms = (time.time() - start) * 1000
                        return True
            
            elif self.ai_type == "mcp":
                # MCP协议连接
                self.status = "connected"
                self.last_contact = time.time()
                return True
            
            return False
        except Exception:
            self.status = "error"
            return False
    
    async def execute(self, task: str, timeout: int = 60) -> Dict:
        """
        向AI智能体发送任务
        
        Returns:
            {"success": bool, "result": str, "error": str}
        """
        self.command_count += 1
        start = time.time()
        
        try:
            if self.ai_type == "http_api":
                # 假设对方是ollama-style API
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(
                        f"{self.endpoint}/api/generate",
                        json={"prompt": task, "model": self.name},
                    )
                    if resp.status_code == 200:
                        result = resp.json()
                        self.success_count += 1
                        self.latency_ms = (time.time() - start) * 1000
                        return {"success": True, "result": result.get("response", "")}
                    else:
                        return {"success": False, "error": f"HTTP {resp.status_code}"}
            
            elif self.ai_type == "mcp":
                # 通过MCP协议执行
                if self.collaboration:
                    result = self.collaboration.dispatch_task(self.name, task)
                    self.success_count += 1
                    return {"success": True, "result": result}
                return {"success": False, "error": "Collaboration engine not available"}
            
            else:
                return {"success": False, "error": f"不支持的AI类型: {self.ai_type}"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_stats(self) -> Dict:
        """获取统计"""
        success_rate = (self.success_count / self.command_count * 100) if self.command_count > 0 else 0
        return {
            "name": self.name,
            "type": self.ai_type,
            "endpoint": self.endpoint,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 1),
            "command_count": self.command_count,
            "success_count": self.success_count,
            "success_rate": round(success_rate, 1),
        }


# ============================================================
# 远程控制系统管理器
# ============================================================

class RemoteControlSystem:
    """
    远程控制系统的管理器
    
    整合HTTP服务器和AI客户端，提供完整的远程操控能力。
    """
    
    def __init__(self, port: int = 9999, host: str = "0.0.0.0"):
        self.port = port
        self.host = host
        self.server = None
        self.thread = None
        self.connected_ais: List[ControlledAI] = []
        self.aiclients: Dict[str, AIClient] = {}
        
        # 注入引擎引用
        self.agent_core = None
        self.perception = None
        self.controller = None
        self.memory = None
        self.optimization = None
        self.collaboration = None
    
    def start_server(self):
        """启动HTTP服务器"""
        RemoteControlHandler.agent_core = self.agent_core
        RemoteControlHandler.perception = self.perception
        RemoteControlHandler.controller = self.controller
        RemoteControlHandler.memory = self.memory
        RemoteControlHandler.optimization = self.optimization
        RemoteControlHandler.collaboration = self.collaboration
        
        self.server = HTTPServer((self.host, self.port), RemoteControlHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"🌐 远程控制API已启动: http://{self.host}:{self.port}")
    
    def stop_server(self):
        """停止HTTP服务器"""
        if self.server:
            self.server.shutdown()
            logger.info("🌐 远程控制API已停止")
    
    def connect_ai(self, name: str, ai_type: str, endpoint: str,
                   api_key: str = "", capabilities: List[str] = None) -> bool:
        """
        连接一个新的AI智能体
        
        Args:
            name: AI名称
            ai_type: 类型 (http_api, mcp, ollama, openai_compatible)
            endpoint: 端点地址
            api_key: API密钥
            capabilities: 能力列表
        
        Returns:
            是否成功连接
        """
        client = AIClient(
            name=name,
            ai_type=ai_type,
            endpoint=endpoint,
            api_key=api_key,
            capabilities=capabilities or [],
        )
        
        # 异步连接
        loop = asyncio.new_event_loop()
        connected = loop.run_until_complete(client.connect())
        loop.close()
        
        if connected:
            self.aiclients[name] = client
            
            controlled_ai = ControlledAI(
                id=str(uuid.uuid4())[:8],
                name=name,
                type=ai_type,
                endpoint=endpoint,
                api_key=api_key,
                capabilities=capabilities or [],
                status="connected",
                last_contact=time.time(),
            )
            self.connected_ais.append(controlled_ai)
            
            logger.info(f"🤖 已连接AI: {name} ({ai_type}) @ {endpoint}")
            return True
        else:
            logger.warning(f"❌ 连接AI失败: {name}")
            return False
    
    async def execute_on_ai(self, ai_name: str, task: str, timeout: int = 60) -> Dict:
        """
        在指定的AI上执行任务
        
        Args:
            ai_name: AI名称
            task: 任务描述
            timeout: 超时时间
        
        Returns:
            执行结果
        """
        client = self.aiclients.get(ai_name)
        if not client:
            return {"success": False, "error": f"AI '{ai_name}' 未连接"}
        
        result = await client.execute(task, timeout)
        result["ai_name"] = ai_name
        return result
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            "api_running": self.thread is not None and self.thread.is_alive(),
            "api_port": self.port,
            "connected_ais": len(self.connected_ais),
            "ais": [ai.__dict__ if hasattr(ai, '__dict__') else str(ai) for ai in self.connected_ais],
            "clients": {
                name: client.get_stats()
                for name, client in self.aiclients.items()
            },
        }


# ============================================================
# 快速启动
# ============================================================

def start_remote_control(port: int = 9999, host: str = "127.0.0.1",
                         agent_core=None, perception=None, controller=None,
                         memory=None, optimization=None, collaboration=None):
    """
    快速启动远程控制接口
    
    用法:
        from remote_control import start_remote_control
        
        start_remote_control(
            port=9999,
            agent_core=agent_core,
            perception=perception,
            controller=controller,
        )
        
        # 其他AI可以通过HTTP API操控本Agent:
        # POST http://localhost:9999/api/command
        # {"command": "desktop_status"}
        
        # 本Agent也可以操控其他AI:
        # system.connect_ai("claude", "http_api", "http://localhost:11434")
        # system.execute_on_ai("claude", "搜索今天的AI新闻")
    """
    system = RemoteControlSystem(port=port, host=host)
    system.agent_core = agent_core
    system.perception = perception
    system.controller = controller
    system.memory = memory
    system.optimization = optimization
    system.collaboration = collaboration
    
    system.start_server()
    return system


# 导入依赖
import httpx
