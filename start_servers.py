"""
启动 llama.cpp server (文本 + 视觉模型)
=================================
用 Python 启动代替 .bat 脚本，避免中文路径编码问题。

使用：
    python start_servers.py                 # 启动文本 + 视觉模型
    python start_servers.py --text-only     # 只启动文本模型 (省显存)
    python start_servers.py --vision-only   # 只启动视觉模型
    python start_servers.py --stop          # 停止所有 server
"""
import sys
import os
import time
import signal
import subprocess
import argparse
import httpx
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_DIR))

try:
    import yaml
except ImportError:
    print("缺少 PyYAML，请运行: pip install pyyaml")
    sys.exit(1)


DEFAULT_LLAMA_DIR = PROJECT_DIR / "llama.cpp"


def load_config():
    with open(PROJECT_DIR / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def server_alive(port: int) -> bool:
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def start_server(model_cfg: dict, kind: str) -> subprocess.Popen:
    """启动一个 llama.cpp server，返回进程对象"""
    port = model_cfg["port"]
    if server_alive(port):
        print(f"  [skip] {kind} server already alive on :{port}")
        return None

    model_path = (PROJECT_DIR / model_cfg["path"]).resolve() if not Path(model_cfg["path"]).is_absolute() else Path(model_cfg["path"])
    if not Path(model_path).exists():
        print(f"  [warn] {kind} 模型文件不存在: {model_path}")
        return None

    llama_exe = DEFAULT_LLAMA_DIR / "llama-server.exe"
    if not llama_exe.exists():
        print(f"  [error] llama-server.exe 不存在: {llama_exe}")
        print(f"          请安装 llama.cpp b9616 (CUDA 13.3) 并放到该路径")
        return None

    cmd = [
        str(llama_exe),
        "--model", model_path,
        "--host", "127.0.0.1",
        "--port", str(port),
        "--n-gpu-layers", str(model_cfg.get("n_gpu_layers", 99)),
        "--ctx-size", str(model_cfg.get("context_size", 8192)),
    ]

    # 视觉模型需要 mmproj
    if kind == "vision":
        mmproj = (PROJECT_DIR / model_cfg["mmproj"]).resolve() if model_cfg.get("mmproj") and not Path(model_cfg["mmproj"]).is_absolute() else model_cfg.get("mmproj", "")
        if mmproj and Path(mmproj).exists():
            cmd.extend(["--mmproj", mmproj])
        else:
            print(f"  [warn] 视觉模型缺少 mmproj: {mmproj}")

    print(f"  [start] {kind} on :{port} -> {Path(model_path).name}")
    log_path = PROJECT_DIR / "data" / "logs" / f"{kind}_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")
    log_fh.write(f"\n\n=== start at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    log_fh.flush()

    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(DEFAULT_LLAMA_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return proc


def stop_all_servers():
    """杀掉所有 llama-server 进程"""
    killed = 0
    if os.name == "nt":
        out = subprocess.run(
            ["taskkill", "/F", "/IM", "llama-server.exe"],
            capture_output=True, text=True
        )
        if "SUCCESS" in out.stdout:
            killed = out.stdout.count("SUCCESS")
    else:
        out = subprocess.run(["pkill", "-f", "llama-server"], capture_output=True, text=True)
    print(f"已停止 {killed} 个 llama-server 进程")
    return killed


def wait_ready(port: int, timeout: int = 60):
    """等待 server health 就绪"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if server_alive(port):
            return True
        time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser(description="启动/停止 llama.cpp server")
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--vision-only", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--no-wait", action="store_true", help="不等待 server 就绪")
    args = parser.parse_args()

    if args.stop:
        stop_all_servers()
        return

    cfg = load_config()
    text_cfg = cfg["llama_cpp"]["text_model"]
    vision_cfg = cfg["llama_cpp"]["vision_model"]

    procs = []

    if not args.vision_only:
        p = start_server(text_cfg, "text")
        if p:
            procs.append((p, text_cfg["port"], "text"))

    if not args.text_only:
        p = start_server(vision_cfg, "vision")
        if p:
            procs.append((p, vision_cfg["port"], "vision"))

    if not args.no_wait:
        for proc, port, kind in procs:
            print(f"  [wait] {kind} :{port} 就绪中 ...")
            if wait_ready(port):
                print(f"  [ok]   {kind} :{port} healthy")
            else:
                print(f"  [fail] {kind} :{port} 启动超时")

    if procs:
        print()
        print("所有 server 已启动。按 Ctrl+C 退出 (server 仍在后台运行)。")
        try:
            while True:
                time.sleep(60)
                for proc, port, kind in procs:
                    if proc.poll() is not None:
                        print(f"  [died] {kind} :{port} 进程已退出")
        except KeyboardInterrupt:
            print("\n收到 Ctrl+C。Server 仍在后台运行。stop 用: python start_servers.py --stop")


if __name__ == "__main__":
    main()
