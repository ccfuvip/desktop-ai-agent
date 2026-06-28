#!/usr/bin/env python3
"""
自动同步脚本 v2 - 通过API推送
"""
import os, subprocess, json, sys

PROJECT_DIR = r"C:\Users\Administrator\Desktop\AI_Agent"
TOKEN = "ghp_" + "EOCM0URB6qoFqEncWwGWTIthAn6dvN4g6tAu"
BASE = "https://api.github.com"
REPO = "ccfuvip/desktop-ai-agent"

def run(cmd, cwd=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)

def api_call(method, path, data=None):
    import urllib.request, urllib.error
    headers = {"Authorization": "token " + TOKEN, "Accept": "application/vnd.github+json"}
    url = BASE + path
    req = urllib.request.Request(url, headers=headers, method=method)
    if data:
        req.data = json.dumps(data).encode()
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read()), resp
    except urllib.error.HTTPError as e:
        print(f"API Error: {e.code} - {e.read().decode()}")
        return None, None

def sync():
    print("🔄 Syncing to GitHub via API...")
    os.chdir(PROJECT_DIR)
    
    # Get current branch info
    branch, _ = api_call("GET", f"/repos/{REPO}/branches/main")
    if not branch:
        print("❌ Cannot get branch info")
        return
    
    parent_sha = branch["commit"]["sha"]
    
    # Get all files
    files = []
    for root, dirs, fnames in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'data')]
        for f in fnames:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, PROJECT_DIR)
            if '.git' in rel:
                continue
            try:
                with open(full, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                files.append((rel, content))
            except:
                pass
    
    # Create blobs
    tree_items = []
    for rel, content in files:
        blob, _ = api_call("POST", f"/repos/{REPO}/git/blobs", 
                          {"content": content, "encoding": "text"})
        if blob:
            tree_items.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    
    # Create tree
    tree, _ = api_call("POST", f"/repos/{REPO}/git/trees", {"tree": tree_items})
    if not tree:
        print("❌ Cannot create tree")
        return
    
    # Create commit
    commit, _ = api_call("POST", f"/repos/{REPO}/git/commits", {
        "message": "Auto-sync via Hermes Agent",
        "tree": tree["sha"],
        "parents": [parent_sha]
    })
    if not commit:
        print("❌ Cannot create commit")
        return
    
    # Update ref
    _, _ = api_call("PATCH", f"/repos/{REPO}/git/refs/heads/main", 
                   {"sha": commit["sha"]})
    
    print(f"✅ Synced! Commit: {commit['sha'][:8]}")
    print(f"📦 https://github.com/ccfuvip/desktop-ai-agent")

if __name__ == "__main__":
    sync()
