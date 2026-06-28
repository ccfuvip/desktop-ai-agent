"""
AI Agent 2.0 版本规划
===================
目标：保留框架，根据电脑配置自动选择模型版本，后期做成SETUP安装包

核心改进:
1. 自动硬件检测 + 模型自适应选择
2. llama.cpp 自动下载/管理
3. Setup安装包制作 (PyInstaller)
4. 远程AI操控增强 (MCP协议完善)
5. 自进化系统增强

作者: Desktop AI Agent
版本: 2.0.0-规划
"""


# ============================================================
# 1. 自动硬件检测模块
# ============================================================

def detect_hardware():
    """
    检测当前电脑硬件配置
    
    返回:
        {
            "gpu": {
                "name": "RTX 5080",
                "vram_gb": 16,
                "cuda_version": "13.3",
            },
            "cpu": {
                "name": "Intel i9-13900K",
                "cores": 24,
            },
            "ram_gb": 64,
            "disk_free_gb": 500,
        }
    """
    import psutil
    import subprocess
    
    # GPU检测
    gpu_info = {}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(",")
            gpu_info = {
                "name": parts[0].strip(),
                "vram_gb": int(parts[1].strip()) // 1024,
                "driver_version": parts[2].strip() if len(parts) > 2 else "",
            }
    except Exception:
        pass
    
    if not gpu_info:
        # 无NVIDIA GPU，纯CPU模式
        gpu_info = {"name": "CPU Only", "vram_gb": 0}
    
    # CPU检测
    cpu_info = {
        "name": psutil.cpu_percent(interval=0.1),
        "cores": psutil.cpu_count(logical=True),
    }
    
    # RAM检测
    ram_gb = psutil.virtual_memory().total // (1024**3)
    
    # 磁盘空间
    disk_free_gb = psutil.disk_usage("/").free // (1024**3)
    
    return {
        "gpu": gpu_info,
        "cpu": cpu_info,
        "ram_gb": ram_gb,
        "disk_free_gb": disk_free_gb,
    }


# ============================================================
# 2. 模型自适应选择
# ============================================================

MODEL_SUITABILITY = {
    # 大显存 (>=24GB)
    "high_vram": {
        "text_model": "Hermes-3-70B-Q4_K_M",
        "vision_model": "Qwen2.5-VL-72B-Q4_K_M",
        "llama_cpp_params": {"n_gpu_layers": -1, "tensor_split": None},
        "min_vram_gb": 24,
        "min_cpu_cores": 16,
        "min_ram_gb": 32,
    },
    # 中等显存 (12-23GB)
    "medium_vram": {
        "text_model": "Hermes-3-8B-Q6_K",
        "vision_model": "Qwen2.5-VL-7B-Q6_K",
        "llama_cpp_params": {"n_gpu_layers": 35, "tensor_split": None},
        "min_vram_gb": 12,
        "min_cpu_cores": 8,
        "min_ram_gb": 16,
    },
    # 低显存 (6-11GB)
    "low_vram": {
        "text_model": "Hermes-3-8B-Q4_K_M",
        "vision_model": "Qwen2.5-VL-7B-Q4_K_M",
        "llama_cpp_params": {"n_gpu_layers": 25, "tensor_split": None},
        "min_vram_gb": 6,
        "min_cpu_cores": 4,
        "min_ram_gb": 8,
    },
    # 纯CPU (<6GB)
    "cpu_only": {
        "text_model": "Hermes-3-8B-Q4_K_S",
        "vision_model": "Qwen2.5-VL-7B-Q4_K_S",
        "llama_cpp_params": {"n_gpu_layers": 0, "tensor_split": None},
        "min_vram_gb": 0,
        "min_cpu_cores": 4,
        "min_ram_gb": 8,
    },
}


def select_best_model(hardware: dict) -> dict:
    """
    根据硬件配置选择最佳模型配置
    
    Args:
        hardware: detect_hardware() 返回的硬件信息
        
    Returns:
        最佳模型配置字典
    """
    vram = hardware.get("gpu", {}).get("vram_gb", 0)
    cores = hardware.get("cpu", {}).get("cores", 4)
    ram = hardware.get("ram_gb", 8)
    
    # 从最优到最差匹配
    for category, config in MODEL_SUITABILITY.items():
        if (vram >= config["min_vram_gb"] and
            cores >= config["min_cpu_cores"] and
            ram >= config["min_ram_gb"]):
            return {
                "category": category,
                "text_model": config["text_model"],
                "vision_model": config["vision_model"],
                "llama_cpp_params": config["llama_cpp_params"],
                "hardware_match": hardware,
            }
    
    # 兜底：CPU模式
    return {
        "category": "cpu_only",
        "text_model": MODEL_SUITABILITY["cpu_only"]["text_model"],
        "vision_model": MODEL_SUITABILITY["cpu_only"]["vision_model"],
        "llama_cpp_params": MODEL_SUITABILITY["cpu_only"]["llama_cpp_params"],
        "hardware_match": hardware,
    }


# ============================================================
# 3. llama.cpp 自动管理
# ============================================================

class LLamaCPPManager:
    """
    llama.cpp 自动管理工具
    
    功能:
    - 自动下载最新llama.cpp build
    - 自动下载/切换模型
    - 自动配置CUDA版本
    """
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.models_dir = Path(base_dir) / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
    
    def get_latest_llama_cpp(self) -> str:
        """获取最新版llama.cpp的下载链接"""
        import httpx
        
        # GitHub Releases API
        url = "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
        try:
            with httpx.Client() as client:
                resp = client.get(url, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for asset in data.get("assets", []):
                        if "cuda" in asset["name"].lower() and asset["name"].endswith(".exe"):
                            return asset["browser_download_url"]
        except Exception:
            pass
        return ""
    
    def download_model(self, model_name: str, quantization: str = "Q6_K") -> str:
        """
        从HuggingFace下载模型
        
        Args:
            model_name: 模型名称 (如 "bartowski/Hermes-3-Llama-3.1-8B-GGUF")
            quantization: 量化级别
            
        Returns:
            本地模型文件路径
        """
        import httpx
        
        hf_repo = model_name
        q_file = f"{model_name.split('/')[-1]}-{quantization}.gguf"
        local_path = self.models_dir / q_file
        
        if local_path.exists():
            return str(local_path)
        
        # 从HuggingFace下载
        hf_url = f"https://huggingface.co/{hf_repo}/resolve/main/{q_file}"
        
        try:
            with httpx.stream("GET", hf_url, timeout=30) as resp:
                if resp.status_code == 200:
                    with open(local_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                    return str(local_path)
        except Exception as e:
            print(f"模型下载失败: {e}")
        
        return ""
    
    def generate_server_cmd(self, model_path: str, params: dict) -> str:
        """生成llama.cpp server命令"""
        cmd = f'./server -m "{model_path}"'
        
        # 添加参数
        gpu_layers = params.get("n_gpu_layers", 35)
        cmd += f" -ngl {gpu_layers}"
        
        threads = params.get("n_threads", 8)
        cmd += f" -t {threads}"
        
        ctx_size = params.get("ctx_size", 4096)
        cmd += f" -c {ctx_size}"
        
        return cmd


# ============================================================
# 4. Setup安装包制作
# ============================================================

def create_installer():
    """
    使用PyInstaller制作Windows安装包
    
    步骤:
    1. 收集所有依赖
    2. 生成spec文件
    3. 打包成单文件或目录
    4. 可选：添加Inno Setup制作真正的安装向导
    
    用法:
        python -m PyInstaller --name="AI_Agent" --onedir \\
            --icon=icons/agent.ico \\
            --add-data "config.yaml;." \\
            --add-data "start_servers.bat;." \\
            ui_main.py
    """
    import subprocess
    from pathlib import Path
    
    project_dir = Path(__file__).parent
    
    # 创建spec文件 — 用 .format() 避免 f-string 内嵌 {} 冲突
    spec_content = """
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{project_dir}/ui_main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('{project_dir}/config.yaml', '.'),
        ('{project_dir}/start_servers.bat', '.'),
        ('{project_dir}/start_agent.bat', '.'),
        ('{project_dir}/requirements.txt', '.'),
    ],
    hiddenimports=[
        'yaml',
        'mss',
        'uiautomation',
        'pyautogui',
        'keyboard',
        'win32gui',
        'win32con',
        'chromadb',
        'httpx',
        'psutil',
        'duckduckgo_search',
        'requests',
        'feedparser',
        'bs4',
        'networkx',
        'remote_control',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    py_modules=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI_Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
""".format(project_dir=str(project_dir))
    
    spec_path = project_dir / "AI_Agent.spec"
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # 执行PyInstaller
    cmd = f'pyinstaller --clean "{spec_path}"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ Setup包创建成功!")
        print(f"输出目录: {project_dir}/dist/")
    else:
        print(f"❌ Setup包创建失败: {result.stderr}")
    
    return spec_path


# ============================================================
# 5. 2.0版本启动脚本
# ============================================================

STARTUP_SCRIPT_20 = '''
#!/bin/bash
# AI Agent 2.0 一键启动脚本
# 自动检测硬件、选择模型、启动服务

echo "=========================================="
echo "  AI Agent 2.0 - 自动配置启动"
echo "=========================================="

# 1. 检测硬件
echo "[1/4] 检测硬件配置..."
python -c "
import sys
sys.path.insert(0, '.')
from ai_agent_20 import detect_hardware, select_best_model
hw = detect_hardware()
model = select_best_model(hw)
gpu_name = hw["gpu"]["name"]
vram = hw["gpu"].get("vram_gb", 0)
cores = hw["cpu"]["cores"]
ram = hw["ram_gb"]
cat = model["category"]
text_m = model["text_model"]
vision_m = model["vision_model"]
print(f'  GPU: {gpu_name} ({vram}GB)')
print(f'  CPU: {cores}核')
print(f'  RAM: {ram}GB')
print(f'  选择模型: {text_m}')
print(f'  模型类别: {cat}')
"

# 2. 检查/下载模型
echo "[2/4] 检查模型文件..."
python -c "
from ai_agent_20 import LLamaCPPManager
mgr = LLamaCPPManager()
# 如果模型不存在则自动下载
"

# 3. 启动llama.cpp服务
echo "[3/4] 启动llama.cpp服务..."
./start_servers.bat

# 4. 启动Agent
echo "[4/4] 启动AI Agent..."
python ui_main.py

echo "=========================================="
echo "  AI Agent 2.0 启动完成!"
echo "=========================================="
'''


# ============================================================
# 6. 2.0版本完整架构
# ============================================================

ARCHITECTURE_20 = """
AI Agent 2.0 架构
================

┌─────────────────────────────────────────────────────┐
│                  AI Agent 2.0                       │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │  硬件检测    │  │ 模型自适应   │  │ Setup制作    │ │
│  │ Module      │  │ Module      │  │ Module      │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │               │               │          │
│         ▼               ▼               ▼          │
│  ┌─────────────────────────────────────────────┐  │
│  │           Config Manager (自动配置)          │  │
│  └─────────────────────────────────────────────┘  │
│         │                                          │
│  ┌──────▼──────────────────────────────────────┐  │
│  │           Core Engines (保持不变)             │  │
│  │  • awareness_engine                         │  │
│  │  • controller_engine                        │  │
│  │  • multimodal_engine                        │  │
│  │  • agent_core                               │  │
│  │  • memory_store                             │  │
│  │  • learning_engine                          │  │
│  │  • upgrade_engine                           │  │
│  │  • optimization_engine                      │  │
│  │  • collaboration_engine                     │  │
│  │  • remote_control                           │  │
│  └─────────────────────────────────────────────┘  │
│         │                                          │
│  ┌──────▼──────────────────────────────────────┐  │
│  │           UI Layer (保持不变)                 │  │
│  │  • ui_main.py (PyQt6)                       │  │
│  └─────────────────────────────────────────────┘  │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │         Model Backend (自动选择)              │  │
│  │  • llama.cpp (自动下载最新版)                │  │
│  │  • 模型自动下载 (HuggingFace)                │  │
│  │  • CUDA/ROCm/CPU 自动适配                    │  │
│  └─────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘

新增功能:
1. ✅ 自动硬件检测 (GPU/VRAM/CPU/RAM)
2. ✅ 模型自适应选择 (4档配置)
3. ✅ llama.cpp 自动管理 (下载/更新)
4. ✅ 模型自动下载 (HuggingFace)
5. ✅ Setup安装包制作 (PyInstaller)
6. ✅ 远程AI操控接口 (HTTP/MCP)
7. ✅ 操控其他AI智能体 (Client模式)
"""


if __name__ == "__main__":
    print("=" * 50)
    print("AI Agent 2.0 规划")
    print("=" * 50)
    print(ARCHITECTURE_20)
    
    # 测试硬件检测
    print("\n[测试] 硬件检测:")
    hw = detect_hardware()
    print(f"  硬件信息: {json.dumps(hw, indent=2, default=str)}")
    
    # 测试模型选择
    print("\n[测试] 模型选择:")
    model = select_best_model(hw)
    print(f"  选择: {model['category']}")
    print(f"  Text: {model['text_model']}")
    print(f"  Vision: {model['vision_model']}")
