"""
启动桌面 AI Agent (Python 启动器)
===============================
代替 start_agent.bat 避免编码问题。
"""
import sys
import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
VENV_PYTHON = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"

# 选择 Python 解释器
def pick_python():
    """优先用项目 .venv，其次用当前 python，最后回退到系统 python"""
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def main():
    extra = sys.argv[1:]
    py = pick_python()

    if "--gui" in extra:
        extra = [a for a in extra if a != "--gui"] + ["--gui"]

    cmd = [py, str(PROJECT_DIR / "main.py")] + extra
    print(f"启动: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n已中断")


if __name__ == "__main__":
    main()