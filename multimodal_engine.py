"""
多模态引擎 (Multimodal Engine)
=============================
图像、视频、音频的全面理解能力

通过 llama.cpp HTTP API 调用本地模型:
- Qwen2.5-VL-7B → 图像理解
- LLaVA-NeXT-Video-7B → 视频分析
- faster-whisper → 音频转录
- Hermes-3-Llama-3.1-8B → 文本推理

作者: Desktop AI Agent
版本: 1.0.0
"""

import time
import base64
import logging
import httpx
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class VisionResult:
    """视觉理解结果"""
    success: bool = False
    description: str = ""
    objects: List[str] = field(default_factory=list)
    text_detected: str = ""
    action_recommendation: str = ""
    error: str = ""
    model_used: str = ""
    latency_ms: float = 0.0


@dataclass
class AudioResult:
    """音频转录结果"""
    success: bool = False
    text: str = ""
    language: str = ""
    segments: List[Dict] = field(default_factory=list)
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class TextResult:
    """文本推理结果"""
    success: bool = False
    content: str = ""
    thought: str = ""
    action: Optional[Dict] = None
    error: str = ""
    latency_ms: float = 0.0
    model_used: str = ""
    finish_reason: str = ""
    usage: Optional[Dict] = None


class MultimodalEngine:
    """
    多模态处理引擎
    
    通过 llama.cpp server 的 HTTP API 调用本地模型。
    
    连接配置:
    - 文本模型: http://127.0.0.1:8080
    - 视觉模型: http://127.0.0.1:8081
    
    使用示例:
        engine = MultimodalEngine()
        
        # 图像理解
        result = engine.analyze_image("./screenshot.png", "这是什么页面？")
        
        # 文本推理
        result = engine.chat("帮我分析这个桌面截图")
        
        # 截图分析 (自动截取当前屏幕)
        result = engine.analyze_screenshot("当前窗口是什么？")
    """
    
    def __init__(self, text_port: int = 8080, vision_port: int = 8081):
        self.text_url = f"http://127.0.0.1:{text_port}"
        self.vision_url = f"http://127.0.0.1:{vision_port}"
        self._client = httpx.Client(timeout=120.0)
        self._health = {"text": False, "vision": False}
        self._check_health()
    
    def __del__(self):
        try:
            self._client.close()
        except Exception:
            pass
    
    def _check_health(self) -> None:
        """检查模型服务健康状态"""
        for port, key in [(8080, "text"), (8081, "vision")]:
            url = f"http://127.0.0.1:{port}/health"
            try:
                resp = self._client.get(url, timeout=5)
                self._health[key] = resp.status_code == 200
            except Exception:
                self._health[key] = False
    
    def is_ready(self, model_type: str = "all") -> bool:
        """检查模型是否就绪"""
        if not self._client.is_closed:
            self._check_health()
        if model_type == "all":
            return self._health["text"] and self._health["vision"]
        return self._health.get(model_type, False)
    
    # ---- 图像理解 ----
    
    def analyze_image(self, image_path: str, prompt: str = "描述这张图片") -> VisionResult:
        """
        分析图像
        
        Args:
            image_path: 图片文件路径
            prompt: 分析问题
            
        Returns:
            VisionResult
        """
        start = time.time()
        
        try:
            # 读取图片并转为base64
            img_data = Path(image_path).read_bytes()
            b64 = base64.b64encode(img_data).decode()
            
            # 调用视觉模型
            resp = self._client.post(
                f"{self.vision_url}/v1/chat/completions",
                json={
                    "model": "qwen2.5-vl",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            {"type": "text", "text": prompt},
                        ]
                    }],
                    "max_tokens": 1024,
                    "temperature": 0.3,
                },
                timeout=180,
            )
            
            if resp.status_code == 200:
                result = resp.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                return VisionResult(
                    success=True,
                    description=content,
                    model_used="Qwen2.5-VL-7B",
                    latency_ms=(time.time() - start) * 1000,
                )
            else:
                return VisionResult(
                    success=False,
                    error=f"HTTP {resp.status_code}: {resp.text[:200]}",
                    latency_ms=(time.time() - start) * 1000,
                )
        
        except Exception as e:
            return VisionResult(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start) * 1000,
            )
    
    def analyze_screenshot(self, prompt: str = "描述这张截图") -> VisionResult:
        """分析当前屏幕截图"""
        try:
            from awareness_engine import DesktopAwarenessEngine
            engine = DesktopAwarenessEngine()
            screenshot_bytes = engine.capture_screen()
            
            if not screenshot_bytes:
                return VisionResult(success=False, error="截图失败")
            
            # 保存到临时文件
            temp_path = "./data/screenshots/temp_analysis.png"
            Path(temp_path).parent.mkdir(parents=True, exist_ok=True)
            Path(temp_path).write_bytes(screenshot_bytes)
            
            return self.analyze_image(temp_path, prompt)
        
        except Exception as e:
            return VisionResult(success=False, error=str(e))
    
    # ---- 文本推理 ----
    
    def chat(self, messages: List[Dict], system_prompt: str = "") -> TextResult:
        """
        文本推理对话
        
        Args:
            messages: 对话消息列表
            system_prompt: 系统提示词
            
        Returns:
            TextResult
        """
        start = time.time()
        
        try:
            payload = {
                "model": "hermes-3-llama-3.1-8b",
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.5,
                "stream": False,
            }
            
            if system_prompt:
                payload["messages"] = [
                    {"role": "system", "content": system_prompt}
                ] + messages
            
            resp = self._client.post(
                f"{self.text_url}/v1/chat/completions",
                json=payload,
                timeout=120,
            )
            
            if resp.status_code == 200:
                result = resp.json()
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                # 尝试解析 ReAct 输出
                thought, action = self._parse_react_output(content)
                
                return TextResult(
                    success=True,
                    content=content,
                    thought=thought,
                    action=action,
                    model_used="Hermes-3-Llama-3.1-8B",
                    latency_ms=(time.time() - start) * 1000,
                )
            else:
                return TextResult(
                    success=False,
                    error=f"HTTP {resp.status_code}",
                    latency_ms=(time.time() - start) * 1000,
                )
        
        except Exception as e:
            return TextResult(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start) * 1000,
            )
    
    def think_and_act(self, user_message: str, desktop_context: dict = None,
                      system_prompt: str = "", memory_context: str = "") -> TextResult:
        """
        Agent核心推理方法: 思考 + 行动决策
        
        这是Agent的"大脑"，接收用户消息和桌面上下文，输出思考和行动。
        
        Args:
            user_message: 用户消息
            desktop_context: 当前桌面状态
            system_prompt: 系统提示词
            memory_context: 相关记忆
            
        Returns:
            TextResult (包含 thought, action, content)
        """
        messages = []
        
        # 构建完整上下文
        context_parts = []
        
        if desktop_context:
            context_parts.append(f"\n\n【当前桌面状态】\n{self._format_desktop_context(desktop_context)}")
        
        if memory_context:
            context_parts.append(f"\n\n【相关经验】\n{memory_context}")
        
        user_content = "".join(context_parts)
        if user_content:
            user_content += f"\n\n【用户指令】\n{user_message}"
        else:
            user_content = user_message
        
        messages.append({"role": "user", "content": user_content})
        
        return self.chat(messages, system_prompt)
    
    # ---- 辅助方法 ----
    
    def _parse_react_output(self, text: str) -> tuple:
        """
        解析 ReAct 输出
        
        从LLM输出中提取 thought 和 action
        """
        thought = text
        action = None
        
        # 尝试提取 JSON action
        import json
        try:
            # 查找 JSON 块
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                action = json.loads(json_str)
                thought = text[:start].strip()
        except (json.JSONDecodeError, ValueError):
            pass
        
        return thought, action
    
    def _format_desktop_context(self, context: dict) -> str:
        """格式化桌面上下文"""
        lines = []
        
        if context.get("active_window"):
            aw = context["active_window"]
            lines.append(f"- 活跃窗口: {aw.get('title', '未知')}")
        
        if context.get("mouse_position"):
            mx, my = context["mouse_position"]
            lines.append(f"- 鼠标位置: ({mx}, {my})")
        
        if context.get("window_list"):
            lines.append(f"- 窗口数量: {context.get('total_windows', 0)}")
            for w in context["window_list"][:5]:
                fg = " [前台]" if w.get("is_foreground") else ""
                lines.append(f"  • {w.get('title', '未知')}{fg}")
        
        return "\n".join(lines)
    
    def get_health(self) -> Dict[str, bool]:
        """获取模型服务健康状态"""
        self._check_health()
        return self._health.copy()
    
    def get_stats(self) -> Dict:
        """获取引擎统计"""
        return {
            "health": self._health,
            "text_url": self.text_url,
            "vision_url": self.vision_url,
        }
