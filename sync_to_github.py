#!/usr/bin/env python3
"""
自动同步脚本：将 AI_Agent 目录的变更推送到 GitHub
用法: python sync_to_github.py
"""
import os
import subprocess
import json
import sys

PROJECT_DIR = r"C:\Users\Administrator\Desktop\AI_Agent"
REMOTE_NAME = "origin"
BRANCH = "main"

def run_cmd(cmd, cwd=None):
    """运行命令并返回输出"""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()

def sync():
    print("=" * 50)
    print("🔄 自动同步: AI_Agent -> GitHub")
    print("=" * 50)
    
    os.chdir(PROJECT_DIR)
    
    # 1. 检查是否有变更
    rc, stdout, stderr = run_cmd("git status --porcelain")
    if not stdout:
        print("✅ 没有需要提交的变更")
        return
    
    print("📝 检测到变更:")
    print(stdout)
    
    # 2. 添加所有变更
    run_cmd("git add -A")
    
    # 3. 提交
    rc, stdout, stderr = run_cmd('git commit -m "Auto-sync: ' + 
                                  subprocess.run("git status --short", shell=True, capture_output=True, text=True).stdout.strip().replace('"', '\\"') + '"')
    if rc != 0:
        print("⚠️ 提交失败:", stderr)
        return
    print("✅ 已提交")
    
    # 4. 推送到GitHub
    rc, stdout, stderr = run_cmd("git push " + REMOTE_NAME + " " + BRANCH)
    if rc != 0:
        print("❌ 推送失败:", stderr)
        print("💡 请检查网络连接或手动推送")
        return
    
    print("✅ 已推送到 GitHub")
    print("📦 仓库: https://github.com/ccfuvip/desktop-ai-agent")
    print("=" * 50)

if __name__ == "__main__":
    sync()
