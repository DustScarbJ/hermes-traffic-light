#!/usr/bin/env python3
"""
Hermes Traffic Light — 系统托盘红绿灯 + Web 界面
监控 Hermes Agent 的工作状态

  🔴 红灯: 正在执行（标准红绿灯语义 — 停，别打扰）
  🟡 黄灯: 等待用户
  🟢 绿灯: 空闲

v6 — 闪烁 + 开机自启版
  - 🔴 执行中红灯慢闪 | 🟡 等用户黄灯快闪 | 🟢 空闲常亮
  - 右键菜单「开机自启」开关
  - 修正颜色语义：红灯=执行中，绿灯=空闲
"""

import json
import logging
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════
#  日志
# ═══════════════════════════════════════════════════════════

LOG_PATH = Path(__file__).parent / "traffic_light.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("Hermes-TL")

log.info("=" * 50)
log.info("启动… Python %s PID=%d", sys.version.split()[0], os.getpid())

# ── PyQt6 ──

try:
    from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal, QObject
    from PyQt6.QtGui import QAction, QIcon, QPainter, QPixmap, QColor, QBrush, QPen
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    log.info("PyQt6 OK")
except ImportError as e:
    log.error("❌ 缺少 PyQt6: %s", e)
    log.error("请执行: pip install PyQt6")
    input("按 Enter 退出…")
    sys.exit(1)

# ── 配置 ──

_HERMES_HOME = Path(os.environ.get("HERMES_HOME", "")) or Path.home() / "AppData" / "Local" / "hermes"
if not _HERMES_HOME.exists():
    _HERMES_HOME = Path.home() / ".hermes"
STATE_DB = _HERMES_HOME / "state.db"
API_HOST, API_PORT = "127.0.0.1", 8642
WEB_PORT = 19876
POLL_MS = 1500
PROC_CACHE_SECS = 6
DEEP_INTERVAL = 4
ICON_SIZE = 48
LIGHT_R = 7
_HERMES_EXE_NAMES = (b"hermes.exe", b"hermes-desktop.exe", b"hermes_desktop.exe")

# ── 开机自启路径 ──
_STARTUP_LNK = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "HermesTrafficLight.lnk"

log.info("state.db = %s  %s", STATE_DB, "存在" if STATE_DB.exists() else "不存在")
log.info("API = %s:%d  Web = http://127.0.0.1:%d", API_HOST, API_PORT, WEB_PORT)


# ═══════════════════════════════════════════════════════════
#  HTML 页面（发光红绿灯）
# ═══════════════════════════════════════════════════════════

_HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes 工作状态</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    user-select: none;
  }
  .container { display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .light-box {
    background: #161b22; border-radius: 24px; padding: 24px 36px;
    display: flex; flex-direction: column; gap: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }
  .light { width: 96px; height: 96px; border-radius: 50%; transition: all 0.3s ease; }
  .light-red    { background: #2d1515; }
  .light-yellow { background: #2d2510; }
  .light-green  { background: #152d20; }
  .light-red.on    { background: #ff3333; box-shadow: 0 0 50px #ff3333cc, 0 0 100px #ff222266; }
  .light-yellow.on { background: #ffaa00; box-shadow: 0 0 50px #ffaa00cc, 0 0 100px #ff880066; }
  .light-green.on  { background: #33ff55; box-shadow: 0 0 50px #33ff55cc, 0 0 100px #22ff4466; }
  .label { text-align: center; font-size: 14px; color: #8b949e; margin-top: 4px; }
  .label .active { color: #e6edf3; font-weight: bold; }
  .status-text { font-size: 13px; color: #484f58; margin-top: 8px; text-align: center; }
  .mode-badge { font-size: 11px; color: #58a6ff; margin-top: 6px; }
  .footer { font-size: 11px; color: #484f58; margin-top: 16px; }
</style>
</head>
<body>
<div class="container">
  <div class="light-box">
    <div class="light light-red" id="l-red"></div>
    <div class="label"><span id="lb-red">🔴 正在执行</span></div>
    <div class="light light-yellow" id="l-yellow"></div>
    <div class="label"><span id="lb-yellow">🟡 等待用户</span></div>
    <div class="light light-green" id="l-green"></div>
    <div class="label"><span id="lb-green">🟢 空闲</span></div>
  </div>
  <div class="status-text"><span id="status-icon">⚫</span> <span id="status-text">检测中…</span></div>
  <div class="mode-badge">基于 state.db + API 实时判断</div>
  <div class="footer">Hermes Traffic Light</div>
</div>
<script>
  let current = 'off';
  const STATUS = {
    red:    { icon: '🔴', text: 'Hermes 正在执行任务', title: '正在执行' },
    yellow: { icon: '🟡', text: '等待用户确认或输入',  title: '等待用户' },
    green:  { icon: '🟢', text: '空闲中，等待下一个任务',title: '空闲' },
    off:    { icon: '⚫', text: 'Hermes 未检测到',    title: '离线' },
  };
  async function poll() {
    try {
      const r = await (await fetch('/state')).json();
      const st = r.state || 'off';
      if (st === current) return;
      document.querySelectorAll('.light').forEach(e => e.classList.remove('on'));
      document.querySelectorAll('.label span').forEach(e => e.classList.remove('active'));
      if (st !== 'off') {
        const el = document.getElementById('l-' + st);
        if (el) el.classList.add('on');
        const lb = document.getElementById('lb-' + st);
        if (lb) lb.classList.add('active');
      }
      const info = STATUS[st] || STATUS.off;
      document.getElementById('status-icon').textContent = info.icon;
      document.getElementById('status-text').textContent = info.text + (r.timestamp ? ' \u00b7 ' + r.timestamp : '');
      document.title = info.title + ' - Hermes';
      current = st;
    } catch(e) {}
  }
  setInterval(poll, 500); poll();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════
#  Web 服务器
# ═══════════════════════════════════════════════════════════

class StateHandler(BaseHTTPRequestHandler):
    _state_getter = None

    def do_GET(self):
        if self.path == '/state':
            st = StateHandler._state_getter() if StateHandler._state_getter else {}
            body = json.dumps(st, ensure_ascii=False).encode()
            ctype = 'application/json'
        else:
            body = _HTML_PAGE.encode('utf-8')
            ctype = 'text/html; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def start_web_server(getter):
    StateHandler._state_getter = getter
    srv = HTTPServer(('127.0.0.1', WEB_PORT), StateHandler)
    srv.allow_reuse_address = True
    log.info("Web 服务器已启动 → http://127.0.0.1:%d", WEB_PORT)
    srv.serve_forever()


# ═══════════════════════════════════════════════════════════
#  核心检测逻辑
# ═══════════════════════════════════════════════════════════

class ProcessDetector:
    """Windows 环境下的 Hermes 进程检测 + CPU 活动监控。
    
    CPU 监控用于 detect state.db 未刷新的实时状态（如 clarify 等待期间）。
    """

    def __init__(self):
        self._cache: Optional[bool] = None
        self._cache_at: float = 0.0
        self._self_pid = os.getpid()
        self._prev_cpu: dict[int, float] = {}
        self._cpu_active_at: Optional[float] = None
        self._cpu_idle_at: Optional[float] = None

    def _is_self(self, pid: int, cmdline: bytes = b"") -> bool:
        if pid == self._self_pid:
            return True
        if not cmdline:
            return False
        return b"traffic_light" in cmdline.lower() or b"hermes_traffic" in cmdline.lower()

    def _quick_check(self) -> bool:
        for name in _HERMES_EXE_NAMES:
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name.decode()}", "/NH"],
                    capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                if name in out:
                    return True
            except Exception:
                pass
        return False

    def _cli_check(self) -> bool:
        try:
            r = subprocess.run(
                ["hermes", "--version"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _deep_check(self) -> bool:
        try:
            out = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'",
                 "get", "processid,commandline", "/format:csv"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout.lower()
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    pid = int(line.rsplit(b",", 1)[-1].strip())
                except (ValueError, IndexError):
                    continue
                if self._is_self(pid, line):
                    continue
                for kw in (b"hermes_cli", b"hermes_agent", b"tui_gateway",
                           b"hermes-agent", b"hermes "):
                    if kw in line:
                        return True
            return False
        except Exception:
            return False

    def present(self, allow_deep: bool = False) -> bool:
        now = time.time()
        if self._cache is not None and (now - self._cache_at) < PROC_CACHE_SECS:
            return self._cache
        r = self._quick_check() or self._cli_check()
        if not r and allow_deep:
            r = self._deep_check()
        self._cache, self._cache_at = r, now
        return r

    def invalidate(self):
        self._cache = None

    # ── CPU 活动检测（用于实时状态判断） ──

    def _get_hermes_pid_list(self) -> list[int]:
        """获取当前 Hermes 进程的 PID 列表。"""
        pids = []
        for name in _HERMES_EXE_NAMES:
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {name.decode()}", "/FO", "CSV", "/NH"],
                    capture_output=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                for line in out.splitlines():
                    parts = line.decode("utf-8", errors="replace").split(",")
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1].strip().strip('"'))
                            if pid != self._self_pid:
                                pids.append(pid)
                        except ValueError:
                            pass
            except Exception:
                pass
        return pids

    def _get_cpu_seconds(self, pids: list[int]) -> dict[int, float]:
        """通过 wmic 获取指定 PID 的 CPU 时间（秒）。"""
        cpu = {}
        for pid in pids:
            try:
                out = subprocess.run(
                    ["wmic", "process", "where", f"processid={pid}",
                     "get", "KernelModeTime,UserModeTime", "/format:csv"],
                    capture_output=True, timeout=3,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                ).stdout
                for line in out.splitlines():
                    parts = line.decode("utf-8", errors="replace").split(",")
                    # 跳过标题行和空行 — 只有数字行才是有效数据
                    if len(parts) >= 3 and parts[-2].strip().isdigit() and parts[-1].strip().isdigit():
                        kt = int(parts[-2].strip())
                        ut = int(parts[-1].strip())
                        cpu[pid] = (kt + ut) / 10_000_000  # 100ns → seconds
                        break
            except Exception:
                pass
        return cpu

    def check_cpu_active(self) -> Optional[bool]:
        """检查 Hermes 进程 CPU 是否活跃。
        
        Returns:
            True  → CPU 活跃（正在工作）
            False → CPU 空闲（等待/挂起）
            None  → 无法检测
        """
        now = time.time()
        pids = self._get_hermes_pid_list()
        if not pids:
            self._cpu_active_at = None
            self._cpu_idle_at = None
            return None

        cpu_now = self._get_cpu_seconds(pids)
        if not cpu_now:
            return None

        # 检查是否有任何 Hermes 进程的 CPU 时间在增长
        active = False
        for pid, secs in cpu_now.items():
            prev = self._prev_cpu.get(pid, secs)
            diff = secs - prev
            if diff > 0.01:  # CPU 时间增长超过 10ms → 活跃
                active = True

        self._prev_cpu = cpu_now

        if active:
            self._cpu_active_at = now
            self._cpu_idle_at = None
            return True
        else:
            if self._cpu_idle_at is None:
                self._cpu_idle_at = now
            return False

    def cpu_idle_seconds(self) -> Optional[float]:
        """返回 Hermes 进程已空闲的秒数。"""
        if self._cpu_idle_at is not None:
            return time.time() - self._cpu_idle_at
        return None


class StateDB:
    def __init__(self):
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure(self):
        if self._conn is not None:
            return
        if not STATE_DB.exists():
            raise FileNotFoundError(str(STATE_DB))
        self._conn = sqlite3.connect(
            f"file:{STATE_DB}?mode=ro", uri=True, timeout=2,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA query_only = 1")

    def close(self):
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def get_active_session(self) -> Optional[dict]:
        try:
            self._ensure()
            rows = self._conn.execute(
                """SELECT id, started_at, ended_at, end_reason, title, message_count
                     FROM sessions WHERE archived = 0
                     ORDER BY started_at DESC LIMIT 10"""
            ).fetchall()
            for r in rows:
                if r[2] is None:
                    return dict(zip(("id", "sa", "ea", "er", "ti", "mc"), r))
            if rows:
                return dict(zip(("id", "sa", "ea", "er", "ti", "mc"), rows[0]))
        except Exception:
            pass
        return None

    def last_msg(self, sid: str) -> Optional[dict]:
        try:
            self._ensure()
            row = self._conn.execute(
                """SELECT role, content, tool_call_id, tool_calls, timestamp, tool_name
                     FROM messages WHERE session_id = ?
                     ORDER BY id DESC LIMIT 1""", (sid,)
            ).fetchone()
            if row:
                return dict(zip(("role", "ct", "tcid", "tc", "ts", "tn"), row))
        except Exception:
            pass
        return None


# ── 辅助函数 ──

def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex((host, port))
        s.close()
        return r == 0
    except Exception:
        return False


def _parse_tool_calls(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    raw = raw.strip()
    if raw in ("", "[]", "{}"):
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _has_clarify_tool(tool_calls: list) -> bool:
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("function", {}).get("name", "") or tc.get("name", "")
            if name.lower() == "clarify":
                return True
    return False


def _check_api() -> Optional[str]:
    if not _port_open(API_HOST, API_PORT, 0.3):
        return None
    try:
        req = urllib.request.Request(
            f"http://{API_HOST}:{API_PORT}/health/detailed",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1) as r:
            d = json.loads(r.read().decode())
            if d.get("active_agents", 0) > 0 or d.get("gateway_busy", False):
                return "busy"
            return "idle"
    except Exception:
        return None


def _determine_status(proc: ProcessDetector, db: StateDB, allow_deep: bool = False) -> str:
    """状态机: 标准红绿灯语义 — 🔴=执行中 🟡=等用户 🟢=空闲。

    结合 state.db 消息检测 + CPU 活动检测：
      - state.db 实时反映已完成 turn 的状态（消息级别的检测）
      - CPU 监控捕获 state.db 未刷新的实时状态（如 clarify 等待期间）

    判断优先级:
      1. 进程未运行 / 无会话 → 绿
      2. state.db 消息级别检测（已完成 turn 的数据）
         - assistant + clarify → 🟡
         - tool + clarify → 🟡
         - assistant + 其他 tc / tool / system / user <30s → 🔴
      3. CPU 活动检测（实时，捕获 state.db 未刷新场景）
         - CPU 活跃 → 🔴（正在工作但 state.db 还未提交）
         - CPU 空闲 <30s → 🟡（等用户，如 clarify 选项展示中）
         - CPU 空闲 >30s / 无法检测 → 🟢（真正空闲）
    """
    now = time.time()

    # 1. 进程检测
    if not proc.present(allow_deep=allow_deep):
        return "green"

    # 2. 活跃会话
    sess = db.get_active_session()
    if sess is None or sess["ea"] is not None:
        return "green"

    # 3. state.db 消息级别检测
    msg = db.last_msg(sess["id"])
    if msg is not None:
        role = msg["role"]
        age = now - msg["ts"]
        tc_list = _parse_tool_calls(msg.get("tc"))
        has_tc = len(tc_list) > 0
        tn = msg.get("tn") or ""

        log.debug("DB: role=%s age=%.0fs tc=%d tn=%s", role, age, len(tc_list), tn)

        # 🟡 黄灯（DB 已刷新场景）
        if role == "assistant" and has_tc and _has_clarify_tool(tc_list):
            return "yellow"
        if role == "tool" and tn == "clarify":
            return "yellow"

        # 🔴 红灯（DB 已刷新场景）
        if role == "assistant" and has_tc:
            return "red"
        if role in ("tool", "system"):
            return "red"
        if role == "user" and age < 30:
            return "red"

    # 4. 实时 CPU 检测（DB 未刷新场景 — 如 clarify 等待期间）
    #    此时 state.db 显示空闲，但 Hermes 进程正在运行
    cpu_active = proc.check_cpu_active()
    if cpu_active is True:
        # CPU 活跃 → 正在工作但 state.db 还未提交
        return "red"

    # CPU 空闲: 检查 CPU 上次活跃时间
    # 如果刚活跃过然后变空闲 → mid-turn 等待中（clarify等）
    # 如果很久没活跃了 → 两轮对话之间，真正空闲
    cpu_active_at = proc._cpu_active_at
    if cpu_active_at is not None and (now - cpu_active_at) < 60:
        # 60s 内 CPU 活跃过 → agent 在中间等待（clarify / 等用户确认）
        return "yellow"

    # 5. API Server 快速检测
    api = _check_api()
    if api == "busy":
        return "red"

    # 🟢 绿灯
    return "green"


# ═══════════════════════════════════════════════════════════
#  图标绘制
# ═══════════════════════════════════════════════════════════

_LIT = {"red": QColor("#ff3b30"), "yellow": QColor("#ffcc00"), "green": QColor("#34c759")}
_DIM = {"red": QColor("#3a0a0a"), "yellow": QColor("#3a2e00"), "green": QColor("#0a2a0a")}

_LABELS = {
    "red": "🔴 正在执行",
    "yellow": "🟡 等待用户",
    "green": "🟢 空闲",
    "off": "⚫ 未检测到",
}
_TIPS = {
    "red": "Hermes Agent 正在执行任务",
    "yellow": "Hermes Agent 等待用户确认或输入",
    "green": "Hermes Agent 空闲中",
    "off": "Hermes Agent 未检测到",
}

# 闪烁: 不同状态的 blink 间隔（ms），0 = 不闪烁
_BLINK_MS = {"red": 800, "yellow": 400, "green": 0, "off": 0}


def _render_icon(active: str) -> QIcon:
    """绘制带凸起光晕的图标。"""
    pm = QPixmap(ICON_SIZE, ICON_SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#555"), 1))
    p.setBrush(QBrush(QColor("#1a1a1a")))
    p.drawRoundedRect(4, 2, ICON_SIZE - 8, ICON_SIZE - 4, 5, 5)

    cx = ICON_SIZE // 2
    ys = {"red": 12, "yellow": 24, "green": 36}
    for name, y in ys.items():
        if name == active:
            p.setOpacity(0.25)
            p.setBrush(QBrush(_LIT[name]))
            p.setPen(Qt.PenStyle.NoPen)
            g = LIGHT_R + 3
            p.drawEllipse(cx - g, y - g, g * 2, g * 2)
            p.setOpacity(1.0)
            p.setBrush(QBrush(_LIT[name]))
            p.setPen(QPen(QColor("#ddd"), 1))
        else:
            p.setBrush(QBrush(_DIM[name]))
            p.setPen(QPen(QColor("#333"), 1))
        p.drawEllipse(cx - LIGHT_R, y - LIGHT_R, LIGHT_R * 2, LIGHT_R * 2)
    p.end()
    return QIcon(pm)


def _render_icon_dim(active: str) -> QIcon:
    """绘制暗淡版本的图标（用于闪烁时的暗态）。"""
    pm = QPixmap(ICON_SIZE, ICON_SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#555"), 1))
    p.setBrush(QBrush(QColor("#1a1a1a")))
    p.drawRoundedRect(4, 2, ICON_SIZE - 8, ICON_SIZE - 4, 5, 5)

    cx = ICON_SIZE // 2
    ys = {"red": 12, "yellow": 24, "green": 36}
    for name, y in ys.items():
        p.setBrush(QBrush(_DIM[name]))
        p.setPen(QPen(QColor("#333"), 1))
        p.drawEllipse(cx - LIGHT_R, y - LIGHT_R, LIGHT_R * 2, LIGHT_R * 2)
    p.end()
    return QIcon(pm)


# ═══════════════════════════════════════════════════════════
#  后台轮询 Worker
# ═══════════════════════════════════════════════════════════

class PollWorker(QObject):
    status_changed = pyqtSignal(str)
    _latest_state = "off"

    def start(self):
        self._proc = ProcessDetector()
        self._db = StateDB()
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)
        log.info("轮询线程已启动 (间隔 %.1fs)", POLL_MS / 1000)

    def stop(self):
        self._timer.stop()
        self._db.close()

    def _poll(self):
        self._tick += 1
        try:
            allow_deep = (self._tick % DEEP_INTERVAL == 0)
            st = _determine_status(self._proc, self._db, allow_deep)
        except Exception as e:
            log.error("轮询异常: %s", e)
            st = "green"
        PollWorker._latest_state = st
        self.status_changed.emit(st)

    @classmethod
    def current_state(cls) -> dict:
        return {
            "state": cls._latest_state,
            "timestamp": time.strftime("%H:%M:%S"),
            "label": _LABELS.get(cls._latest_state, "未知"),
        }


# ═══════════════════════════════════════════════════════════
#  开机自启工具函数
# ═══════════════════════════════════════════════════════════

def _is_autostart_enabled() -> bool:
    """检查开机自启快捷方式是否存在。"""
    return _STARTUP_LNK.exists()


def _toggle_autostart(enable: bool) -> bool:
    """启用/禁用开机自启。返回操作后的状态。"""
    if enable:
        if _STARTUP_LNK.exists():
            return True  # 已启用
        try:
            # 用 PowerShell 创建快捷方式
            script = _STARTUP_LNK
            ps = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{script}')
$s.TargetPath = 'python.exe'
$s.Arguments = '"F:\\JZT\\Python\\hermes_traffic_light\\traffic_light.py"'
$s.WorkingDirectory = 'F:\\JZT\\Python\\hermes_traffic_light'
$s.WindowStyle = 7
$s.Save()
"""
            subprocess.run(
                ["powershell", "-Command", ps],
                capture_output=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
                check=True,
            )
            log.info("开机自启已启用")
            return True
        except Exception as e:
            log.error("启用开机自启失败: %s", e)
            return False
    else:
        try:
            if _STARTUP_LNK.exists():
                _STARTUP_LNK.unlink()
            log.info("开机自启已禁用")
            return False
        except Exception as e:
            log.error("禁用开机自启失败: %s", e)
            return _STARTUP_LNK.exists()


# ═══════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════

class TrafficLightApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setQuitOnLastWindowClosed(False)
        log.info("GUI 初始化…")

        # 预渲染图标: 正常 + 暗淡（用于闪烁）
        self._icons = {}
        self._icons_dim = {}
        for k in ("off", "red", "yellow", "green"):
            self._icons[k] = _render_icon(k)
            self._icons_dim[k] = _render_icon_dim(k)

        # 系统托盘
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(self._icons["green"])
        self._tray.setToolTip("Hermes Traffic Light")
        self._tray.show()

        # 右键菜单
        m = QMenu()
        self._info = m.addAction("状态: 检测中…")
        self._info.setEnabled(False)
        m.addSeparator()

        a_browser = m.addAction("🌐 在浏览器打开")
        a_browser.triggered.connect(self._open_browser)

        a_refresh = m.addAction("🔄 强制刷新")
        a_refresh.triggered.connect(self._force_refresh)

        m.addSeparator()

        self._a_autostart = QAction("🔌 开机自启", checkable=True)
        self._a_autostart.setChecked(_is_autostart_enabled())
        self._a_autostart.triggered.connect(self._toggle_autostart)
        m.addAction(self._a_autostart)

        m.addSeparator()
        a_quit = m.addAction("退出")
        a_quit.triggered.connect(self.quit)
        self._tray.setContextMenu(m)

        self._last_state: Optional[str] = None
        self._blink_on = True  # blink toggle state
        self._worker_ref: Optional[PollWorker] = None

        # ── 闪烁定时器 ──
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_timer.start(200)  # 基础 tick 200ms

        # ── Web 服务器 ──
        self._web_thread = threading.Thread(
            target=start_web_server,
            args=(PollWorker.current_state,),
            daemon=True,
        )
        self._web_thread.start()

        # ── 后台轮询 ──
        self._thread = QThread(self)
        self._worker = PollWorker()
        self._worker_ref = self._worker
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.status_changed.connect(self._on_status)
        self._thread.start()

        log.info("GUI 就绪")
        log.info("系统托盘已显示  |  Web: http://127.0.0.1:%d  |  日志: %s", WEB_PORT, LOG_PATH)

    def _open_browser(self):
        import webbrowser
        url = f"http://127.0.0.1:{WEB_PORT}"
        webbrowser.open(url)
        log.info("打开浏览器: %s", url)

    def _force_refresh(self):
        if self._worker_ref:
            self._worker_ref._proc.invalidate()
        log.info("强制刷新检测缓存")

    def _toggle_autostart(self, checked: bool):
        """切换开机自启。"""
        result = _toggle_autostart(checked)
        self._a_autostart.setChecked(result)
        log.info("开机自启: %s", "启用" if result else "禁用")

    def _blink_tick(self):
        """每 200ms 触发，根据当前状态决定图标是否闪烁。"""
        st = self._last_state or "green"
        interval = _BLINK_MS.get(st, 0)
        if interval == 0:
            # 不闪烁 → 常亮
            self._tray.setIcon(self._icons.get(st, self._icons["green"]))
            return

        # 闪烁: 根据 interval 决定 toggle 频率
        # 每 blink_interval/200 次 tick 切换一次
        tick_mod = interval // 200
        if tick_mod < 1:
            tick_mod = 1
        # 使用一个计数器做 toggle
        if not hasattr(self, '_blink_counter'):
            self._blink_counter = 0
        self._blink_counter += 1
        if self._blink_counter % tick_mod == 0:
            self._blink_on = not self._blink_on

        if self._blink_on:
            self._tray.setIcon(self._icons.get(st, self._icons["green"]))
        else:
            self._tray.setIcon(self._icons_dim.get(st, self._icons_dim["green"]))

    def _on_status(self, st: str):
        if st == self._last_state:
            return
        self._last_state = st
        self._blink_on = True  # reset blink
        self._blink_counter = 0
        # 立即更新图标（不闪烁时用常亮，闪烁时下次 _blink_tick 接管）
        self._tray.setIcon(self._icons.get(st, self._icons["green"]))
        self._info.setText(f"状态: {_LABELS.get(st, '未知')}")
        self._tray.setToolTip(_TIPS.get(st, "Hermes Traffic Light"))
        log.info("状态 → %s", _LABELS.get(st, st))

    def quit(self):
        log.info("退出中…")
        self._blink_timer.stop()
        if self._worker_ref:
            self._worker_ref.stop()
        if hasattr(self, "_thread"):
            self._thread.quit()
            self._thread.wait(3000)
        super().quit()


def main():
    log.info("main() PID=%d", os.getpid())
    try:
        app = TrafficLightApp(sys.argv)
        sys.exit(app.exec())
    except Exception as e:
        log.error("致命错误: %s", e)
        import traceback
        traceback.print_exc()
        input("按 Enter 退出…")
        sys.exit(1)


if __name__ == "__main__":
    main()
