#!/usr/bin/env python3
"""
Hermes Traffic Light — 诊断工具
检查环境，检测 Hermes 是否可达，新增 Web 端口检测。
用法: python diagnose.py
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path


def ok(msg):
    print(f"  ✅ {msg}")


def fail(msg):
    print(f"  ❌ {msg}")


def info(msg):
    print(f"  ℹ️  {msg}")


def header(title):
    print(f"\n=== {title} ===")


header("Python 环境")
info(f"Python {sys.version.split()[0]}")
info(f"PID = {os.getpid()}")
try:
    from PyQt6.QtCore import PYQT_VERSION_STR
    ok(f"PyQt6 {PYQT_VERSION_STR}")
except ImportError:
    fail("PyQt6 未安装")
    info("请执行: pip install PyQt6")

header("Hermes 进程")
# Hermes.exe
try:
    out = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq Hermes.exe", "/NH"],
        capture_output=True, timeout=5,
        creationflags=subprocess.CREATE_NO_WINDOW,
    ).stdout
    if b"Hermes.exe" in out:
        lines = [l for l in out.splitlines() if b"Hermes.exe" in l]
        ok(f"Hermes.exe 运行中 ({len(lines)} 个进程)")
        for l in lines:
            parts = l.strip().split()
            if len(parts) >= 2:
                try:
                    info(f"  PID={parts[1].decode('gbk', errors='replace')}")
                except Exception:
                    pass
    else:
        fail("未找到 Hermes.exe（可能以 CLI 模式运行）")
except Exception as e:
    fail(f"进程检测出错: {e}")

# hermes CLI
try:
    r = subprocess.run(["hermes", "--version"],
                       capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode == 0:
        ver = r.stdout.decode("utf-8", errors="replace").strip()
        ok(f"hermes CLI: {ver}")
    else:
        fail("hermes CLI 命令失败")
except FileNotFoundError:
    fail("hermes CLI 未安装（不在 PATH 中）")
except Exception as e:
    fail(f"hermes CLI 检测出错: {e}")

header("Hermes API Server (port 8642)")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    if s.connect_ex(("127.0.0.1", 8642)) == 0:
        ok("端口开放")
        s.close()
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:8642/health/detailed",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                d = json.loads(r.read().decode())
                info(f"active_agents = {d.get('active_agents', '?')}")
                info(f"gateway_busy = {d.get('gateway_busy', '?')}")
                if d.get("active_agents", 0) > 0 or d.get("gateway_busy", False):
                    ok("Hermes 正在工作中！")
                else:
                    info("Hermes 空闲中")
        except Exception as e:
            fail(f"HTTP 请求失败: {e}")
    else:
        fail("端口未开放")
        s.close()
        info("如需启用: hermes config set platforms.api_server.enabled true")
        info("然后: hermes gateway restart")
except Exception as e:
    fail(f"socket 检测失败: {e}")

header("state.db")
_hermes_home = Path(os.environ.get("HERMES_HOME", "")) or (
    Path.home() / "AppData" / "Local" / "hermes"
)
if not _hermes_home.exists():
    _hermes_home = Path.home() / ".hermes"
db_path = _hermes_home / "state.db"
if db_path.exists():
    ok(f"存在 ({db_path})")
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
        conn.execute("PRAGMA query_only = 1")
        cnt = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        info(f"sessions 表: {cnt} 行")
        row = conn.execute(
            "SELECT id, started_at, ended_at, end_reason, message_count, title "
            "FROM sessions WHERE archived = 0 ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if row:
            info(f"最新会话: id={row[0][:16]}... ended_at={row[2]} msgs={row[4]}")
            if row[2] is None:
                ok("会话活跃中")
                msg = conn.execute(
                    "SELECT role, tool_calls, timestamp FROM messages "
                    "WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                    (row[0],)
                ).fetchone()
                if msg:
                    has_tc = False
                    tc_raw = msg[1]
                    if tc_raw:
                        try:
                            tc_list = json.loads(tc_raw)
                            has_tc = isinstance(tc_list, (list, dict)) and len(tc_list) > 0
                        except Exception:
                            has_tc = bool(tc_raw.strip() not in ("", "[]", "{}"))
                    info(f"最后消息: role={msg[0]} tool_calls={has_tc} age={time.time()-msg[2]:.0f}s")
                    if has_tc:
                        # 检查是否是 clarify
                        try:
                            tc_list = json.loads(tc_raw) if isinstance(tc_raw, str) else []
                            if isinstance(tc_list, dict):
                                tc_list = [tc_list]
                            for tc in tc_list:
                                name = tc.get("function", {}).get("name", "") or tc.get("name", "")
                                if name.lower() == "clarify":
                                    info("  → 检测到 clarify 工具调用（等待用户确认）")
                        except Exception:
                            pass
                else:
                    info("会话无消息")
            else:
                info("所有会话已结束")
        else:
            info("无会话记录")
        conn.close()
    except Exception as e:
        fail(f"读取失败: {e}")
else:
    fail("state.db 不存在")
    info(f"路径: {db_path}")
    info("Hermes 至少需要运行过一次才会创建该文件")

header("Webhook Server (port 8644)")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    ok("开放" if s.connect_ex(("127.0.0.1", 8644)) == 0 else "未开放")
    s.close()
except Exception as e:
    fail(f"检测失败: {e}")

header("Traffic Light Web UI (port 19876)")
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    if s.connect_ex(("127.0.0.1", 19876)) == 0:
        s.close()
        ok("端口开放 → http://127.0.0.1:19876")
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:19876/state",
                headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as r:
                d = json.loads(r.read().decode())
                info(f"当前状态: {d.get('state', '?')} ({d.get('label', '')})")
                info(f"时间戳: {d.get('timestamp', '')}")
        except Exception as e:
            fail(f"HTTP 请求失败: {e}")
    else:
        s.close()
        fail("端口未开放")
        info("启动 traffic_light.py 后会自动启用")
except Exception as e:
    fail(f"检测失败: {e}")

header("结论")
print()
if db_path.exists():
    info("state.db 可用 → 红绿灯可通过 state.db 检测 Hermes 状态")
else:
    info("state.db 不存在，请先运行 Hermes")
info("建议启用 API Server 获得最佳体验:")
info("  hermes config set platforms.api_server.enabled true")
info("  hermes gateway restart")
print()
