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
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

# ═══════════════════════════════════════════════════════════
#  日志
# ═══════════════════════════════════════════════════════════

# 支持 PyInstaller 冻结模式
if getattr(sys, 'frozen', False):
    APP_DIR = Path(os.path.dirname(os.path.abspath(sys.executable)))
else:
    APP_DIR = Path(__file__).parent

LOG_PATH = APP_DIR / "traffic_light.log"

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
UDP_PORT = 18888           # Hermes Plugin 实时事件端口
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
#  多语言 HTML 页面（发光红绿灯）
# ═══════════════════════════════════════════════════════════

_LANG = "cn"  # 当前语言: cn/en/jp/kr

_LANG_LABELS = {
    "cn": {
        "red": "🔴 已停止", "yellow": "🟡 等待用户", "green": "🟢 正在运行",
        "status_running": "Hermes 正在执行任务",
        "status_idle": "Hermes 已停止",
        "status_wait": "等待用户操作",
        "status_off": "Hermes 未检测到",
        "title_running": "正在运行",
        "title_idle": "已停止",
        "title_wait": "等待用户",
        "title_off": "离线",
        "badge": "实时事件驱动",
        "footer": "Hermes Traffic Light · 实时事件驱动",
    },
    "en": {
        "red": "🔴 Stopped", "yellow": "🟡 Waiting", "green": "🟢 Running",
        "status_running": "Hermes is executing tasks",
        "status_idle": "Hermes stopped",
        "status_wait": "Waiting for user input",
        "status_off": "Hermes not detected",
        "title_running": "Running",
        "title_idle": "Stopped",
        "title_wait": "Waiting",
        "title_off": "Offline",
        "badge": "Real-time event driven",
        "footer": "Hermes Traffic Light · Real-time Event Driven",
    },
    "jp": {
        "red": "🔴 停止中", "yellow": "🟡 待機中", "green": "🟢 実行中",
        "status_running": "Hermes がタスクを実行中",
        "status_idle": "Hermes 停止中",
        "status_wait": "ユーザーの操作を待機中",
        "status_off": "Hermes が検出されていません",
        "title_running": "実行中",
        "title_idle": "停止中",
        "title_wait": "待機中",
        "title_off": "オフライン",
        "badge": "リアルタイムイベント駆動",
        "footer": "Hermes Traffic Light · リアルタイムイベント駆動",
    },
    "kr": {
        "red": "🔴 중지됨", "yellow": "🟡 대기 중", "green": "🟢 실행 중",
        "status_running": "Hermes가 작업을 실행 중입니다",
        "status_idle": "Hermes 중지됨",
        "status_wait": "사용자 입력을 기다리는 중",
        "status_off": "Hermes를 찾을 수 없음",
        "title_running": "실행 중",
        "title_idle": "중지됨",
        "title_wait": "대기 중",
        "title_off": "오프라인",
        "badge": "실시간 이벤트 기반",
        "footer": "Hermes Traffic Light · 실시간 이벤트 기반",
    },
}


def _lang_str(key: str) -> str:
    """获取当前语言的字符串。"""
    return _LANG_LABELS.get(_LANG, _LANG_LABELS["cn"]).get(key, key)


def _set_lang(lang: str):
    """切换语言并持久化到配置文件。"""
    global _LANG
    if lang in _LANG_LABELS:
        _LANG = lang
        try:
            (APP_DIR / ".lang").write_text(lang, encoding="utf-8")
        except Exception:
            pass
        log.info("语言已切换 → %s", lang.upper())


def _load_lang():
    """从持久化文件加载语言。"""
    global _LANG
    try:
        saved = (APP_DIR / ".lang").read_text(encoding="utf-8").strip()
        if saved in _LANG_LABELS:
            _LANG = saved
    except Exception:
        pass


_load_lang()


def _render_html() -> str:
    """生成当前语言的 HTML 页面。"""
    L = _LANG_LABELS.get(_LANG, _LANG_LABELS["cn"])
    js_status = json.dumps({
        "red":    {"icon": "🔴", "text": L["status_idle"], "title": L["title_idle"]},
        "green":  {"icon": "🟢", "text": L["status_running"], "title": L["title_running"]},
        "yellow": {"icon": "🟡", "text": L["status_wait"], "title": L["title_wait"]},
        "off":    {"icon": "⚫", "text": L["status_off"], "title": L["title_off"]},
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="{_LANG}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{L["title_idle"]} - Hermes</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0d1117;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh;
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    user-select: none;
  }}
  .container {{ display: flex; flex-direction: column; align-items: center; gap: 8px; }}
  .light-box {{
    background: #161b22; border-radius: 24px; padding: 24px 36px;
    display: flex; flex-direction: column; gap: 16px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  }}
  .light {{ width: 96px; height: 96px; border-radius: 50%; transition: all 0.3s ease; }}
  .light-red    {{ background: #2d1515; }}
  .light-yellow {{ background: #2d2510; }}
  .light-green  {{ background: #152d20; }}
  .light-red.on    {{ background: #ff3333; box-shadow: 0 0 50px #ff3333cc, 0 0 100px #ff222266; }}
  .light-yellow.on {{ background: #ffaa00; box-shadow: 0 0 50px #ffaa00cc, 0 0 100px #ff880066; }}
  .light-green.on  {{ background: #33ff55; box-shadow: 0 0 50px #33ff55cc, 0 0 100px #22ff4466; }}
  .label {{ text-align: center; font-size: 14px; color: #8b949e; margin-top: 4px; }}
  .label .active {{ color: #e6edf3; font-weight: bold; }}
  .status-text {{ font-size: 13px; color: #484f58; margin-top: 8px; text-align: center; }}
  .mode-badge {{ font-size: 11px; color: #58a6ff; margin-top: 6px; }}
  .footer {{ font-size: 11px; color: #484f58; margin-top: 16px; }}
  .lang-bar {{ display: flex; gap: 6px; margin-top: 12px; }}
  .lang-btn {{
    font-size: 10px; padding: 2px 8px; border-radius: 4px;
    background: #21262d; color: #8b949e; cursor: pointer; border: 1px solid #30363d;
    transition: all 0.2s;
  }}
  .lang-btn.active {{ background: #1f6feb; color: #fff; border-color: #1f6feb; }}
  .lang-btn:hover {{ background: #30363d; }}
</style>
</head>
<body>
<div class="container">
  <div class="light-box">
    <div class="light light-red" id="l-red"></div>
    <div class="label"><span id="lb-red">{L["red"]}</span></div>
    <div class="light light-yellow" id="l-yellow"></div>
    <div class="label"><span id="lb-yellow">{L["yellow"]}</span></div>
    <div class="light light-green" id="l-green"></div>
    <div class="label"><span id="lb-green">{L["green"]}</span></div>
  </div>
  <div class="status-text"><span id="status-icon">⚫</span> <span id="status-text">检测中…</span></div>
  <div class="mode-badge">{L["badge"]}</div>
  <div class="lang-bar">
    <span class="lang-btn{' active' if _LANG=='cn' else ''}" onclick="setLang('cn')">中文</span>
    <span class="lang-btn{' active' if _LANG=='en' else ''}" onclick="setLang('en')">EN</span>
    <span class="lang-btn{' active' if _LANG=='jp' else ''}" onclick="setLang('jp')">日本語</span>
    <span class="lang-btn{' active' if _LANG=='kr' else ''}" onclick="setLang('kr')">한국어</span>
  </div>
  <div class="footer">{L["footer"]}</div>
</div>
<script>
  let current = 'off';
  const LANG = {js_status};
  const LANG_MAP = {{cn:'中文',en:'EN',jp:'日本語',kr:'한국어'}};
  let currentLang = '{_LANG}';

  async function setLang(lang) {{
    await fetch('/lang?lang=' + lang);
    location.reload();
  }}

  function updateLangBar(lang) {{
    document.querySelectorAll('.lang-btn').forEach(b => b.classList.remove('active'));
    const btns = document.querySelectorAll('.lang-btn');
    const keys = ['cn','en','jp','kr'];
    const idx = keys.indexOf(lang);
    if (idx >= 0 && btns[idx]) btns[idx].classList.add('active');
  }}

  async function poll() {{
    try {{
      const r = await (await fetch('/state')).json();
      const st = r.state || 'off';
      if (st === current) return;
      document.querySelectorAll('.light').forEach(e => e.classList.remove('on'));
      document.querySelectorAll('.label span').forEach(e => e.classList.remove('active'));
      if (st !== 'off') {{
        const el = document.getElementById('l-' + st);
        if (el) el.classList.add('on');
        const lb = document.getElementById('lb-' + st);
        if (lb) lb.classList.add('active');
      }}
      const info = LANG[st] || LANG.off;
      document.getElementById('status-icon').textContent = info.icon;
      document.getElementById('status-text').textContent = info.text + (r.timestamp ? ' · ' + r.timestamp : '');
      document.title = info.title + ' - Hermes';
      current = st;
    }} catch(e) {{}}
  }}
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
        elif self.path.startswith('/lang'):
            lang = self.path.split('lang=')[-1] if 'lang=' in self.path else 'cn'
            _set_lang(lang)
            body = b'{"ok":true}'
            ctype = 'application/json'
        else:
            body = _render_html().encode('utf-8')
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
                """SELECT id, started_at, ended_at, end_reason, title, message_count,
                          tool_call_count, api_call_count
                     FROM sessions WHERE archived = 0
                     ORDER BY started_at DESC LIMIT 10"""
            ).fetchall()
            for r in rows:
                if r[2] is None:
                    return dict(zip(("id", "sa", "ea", "er", "ti", "mc", "tcc", "acc"), r))
            if rows:
                return dict(zip(("id", "sa", "ea", "er", "ti", "mc", "tcc", "acc"), rows[0]))
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


# ═══════════════════════════════════════════════════════════
#  事件总线 + 事件驱动 FSM
# ═══════════════════════════════════════════════════════════

from enum import Enum
from typing import Callable, Any

class FsmState(Enum):
    OFFLINE = "offline"
    RUNNING = "running"
    WAIT_USER = "wait_user"
    IDLE = "idle"

FSM_TO_LIGHT = {
    FsmState.OFFLINE: "yellow",
    FsmState.RUNNING: "green",
    FsmState.WAIT_USER: "yellow",
    FsmState.IDLE: "red",
}
FSM_BLINK = {
    FsmState.OFFLINE: 0,
    FsmState.RUNNING: 0,
    FsmState.WAIT_USER: 400,
    FsmState.IDLE: 0,
}
FSM_LABELS = {
    FsmState.OFFLINE: "🟡 离线",
    FsmState.RUNNING: "🟢 正在运行",
    FsmState.WAIT_USER: "🟡 需要操作",
    FsmState.IDLE: "🔴 已停止",
}
FSM_TIPS = {
    FsmState.OFFLINE: "Hermes Agent 未运行或无活跃会话",
    FsmState.RUNNING: "Hermes Agent 正在执行任务",
    FsmState.WAIT_USER: "Hermes Agent 等待用户确认或输入",
    FsmState.IDLE: "Hermes Agent 空闲中 — 未在运行",
}


# 全局外部事件队列 + 双源时钟锁
_external_event_queue: queue.Queue = queue.Queue()
_ui_last_event_at: float = 0.0          # 最近一次 UI 事件时间戳
_ui_immunity_secs: float = 2.0           # UI 事件后免疫 DB 事件的窗口
_ui_immunity_lock: threading.Lock = threading.Lock()


def _ui_immune() -> bool:
    """检查当前是否在 UI 免疫窗口内。"""
    with _ui_immunity_lock:
        return (time.time() - _ui_last_event_at) < _ui_immunity_secs


def start_http_receiver():
    """守护线程：HTTP POST 端点 :18888，接收 Hermes UI Observer 的实时事件。

    UI Observer 发 POST /event:
      {"event":"busy",         "source":"ui", "ts":...}
      {"event":"needs_input",  "source":"ui", "ts":...}
      {"event":"idle",         "source":"ui", "ts":...}
      {"event":"session_end",  "source":"ui", "ts":...}

    Plugin 也可用同一端点（source="plugin"）。
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class EventHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            global _ui_last_event_at
            # CORS 头（允许任意来源的 fetch）
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode("utf-8", errors="replace"))

                ev = payload.get("event", "")
                source = payload.get("source", "unknown")
                detail = payload.get("detail", {})

                if source == "ui":
                    with _ui_immunity_lock:
                        _ui_last_event_at = time.time()

                log.info("HTTP ← event=%s source=%s detail=%s", ev, source, detail)
                _external_event_queue.put(payload)
                self.wfile.write(b'{"ok":true}')
            except Exception as e:
                log.warning("HTTP 处理异常: %s", e)
                try:
                    self.wfile.write(b'{"ok":false}')
                except Exception:
                    pass

        def do_OPTIONS(self):
            """预检请求 CORS。"""
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, *a):
            pass  # 静默日志

    srv = HTTPServer(("127.0.0.1", UDP_PORT), EventHandler)
    srv.timeout = 1.0
    log.info("HTTP 事件接收器已启动 → http://127.0.0.1:%d/event", UDP_PORT)

    while True:
        try:
            srv.handle_request()
        except TimeoutError:
            continue
        except Exception as e:
            log.error("HTTP 接收异常: %s", e)
            break


class HermesEventBus:
    """轻量事件总线 — Runtime → Event → FSM → UI."""

    def __init__(self):
        self._subs: dict[str, list[Callable]] = {}

    def on(self, event: str, cb: Callable):
        self._subs.setdefault(event, []).append(cb)

    def emit(self, event: str, data: dict | None = None):
        for cb in self._subs.get(event, []):
            try:
                cb(data or {})
            except Exception as e:
                log.error("Event[%s] handler error: %s", event, e)


class EventFSM:
    """FSM 不再 poll DB，只接收事件总线的事实。

    双源时钟锁:
      - UI 事件（source="ui"）来自 DOM MutationObserver → 绝对实时、最高优先级
      - DB 事件（从 DbEventSource 来）有 2s 免疫窗口 → 若 UI 刚发过事件则忽略
      - 这修复了「第 5 项 Bug」：DB 回放过期事件覆盖 UI 实时状态
    """

    def __init__(self, bus: HermesEventBus):
        self._state: FsmState = FsmState.IDLE
        # 注册所有事件
        for ev in ("session_start", "session_end", "offline", "online",
                    "tool_start", "tool_end", "clarify_request",
                    "message_user", "message_assistant",
                    "busy", "idle", "needs_input"):
            bus.on(ev, lambda d, e=ev: self._handle(e, d))

    def _handle(self, event: str, data: dict | None):
        """统一事件处理器，含双源时钟锁。"""
        data = data or {}
        source = data.get("source", "db")

        # ── 免疫锁：DB 源事件在 UI 免疫窗口内 → 忽略 ──
        if source == "db" and _ui_immune():
            log.debug("FSM: immune → ignore db event=%s", event)
            return

        # ── 状态转换 ──
        if event in ("session_end", "offline"):
            self._state = FsmState.OFFLINE
            log.info("FSEvent: OFFLINE (%s)", event)

        elif event == "online":
            if self._state == FsmState.OFFLINE:
                self._state = FsmState.IDLE
                log.info("FSEvent: IDLE (online)")

        elif event == "session_start":
            self._state = FsmState.IDLE
            log.info("FSEvent: IDLE (session start)")

        elif event in ("tool_start", "busy"):
            self._state = FsmState.RUNNING
            log.info("FSEvent: RUNNING (%s%s)", event,
                     f" tool={data.get('tool_name','?')}" if event == "tool_start" else "")

        elif event == "tool_end":
            if self._state == FsmState.RUNNING:
                self._state = FsmState.IDLE
                log.info("FSEvent: IDLE (tool end)")

        elif event == "needs_input":
            self._state = FsmState.WAIT_USER
            log.info("FSEvent: WAIT_USER (needs_input)")

        elif event == "clarify_request":
            self._state = FsmState.WAIT_USER
            log.info("FSEvent: WAIT_USER (clarify)")

        elif event == "idle":
            # UI 说空闲了，只有当前不是 OFFLINE 时覆盖
            if self._state != FsmState.OFFLINE:
                self._state = FsmState.IDLE
                log.info("FSEvent: IDLE (ui idle)")

        elif event == "message_user":
            if self._state == FsmState.WAIT_USER:
                self._state = FsmState.RUNNING
                log.info("FSEvent: RUNNING (user msg after clarify)")

    @property
    def state(self) -> FsmState:
        return self._state

    @property
    def light(self) -> str:
        return FSM_TO_LIGHT.get(self._state, "green")

    @property
    def blink_ms(self) -> int:
        return FSM_BLINK.get(self._state, 0)

    @property
    def label(self) -> str:
        return FSM_LABELS.get(self._state, "未知")

    @property
    def tip(self) -> str:
        return FSM_TIPS.get(self._state, "Hermes Traffic Light")


class DbEventSource:
    """高频读取 state.db 变化并发射事件到总线。

    这是唯一接触 DB 的模块。负责将「DB 写入」翻译为「事件」。
    写入到发射之间的延迟 = poll 间隔 (200ms)。

    已知约束: Hermes Desktop 只在 turn 结束时批量写入 DB，
    因此 tool_start/tool_end 等事件在 turn 完成前不可见。
    这是 state.db 架构的固有延迟，非本层问题。
    """

    def __init__(self, bus: HermesEventBus, db: StateDB):
        self._bus = bus
        self._db = db
        self._prev_max_id: int = 0
        self._prev_tool_count: int = 0
        self._prev_was_online: bool = False
        self._initialized: bool = False

    def tick(self):
        """每次 poll 调用一次，检测变化并发射事件。"""
        now = time.time()

        # ── 进程在线检测 ──
        online = _proc_present_check()
        if not self._initialized:
            self._prev_was_online = online
        else:
            if self._prev_was_online and not online:
                self._bus.emit("offline", {"source": "db"})
            elif not self._prev_was_online and online:
                self._bus.emit("online", {"source": "db"})
        self._prev_was_online = online

        if not online:
            self._initialized = True
            return

        # ── 会话检测 ──
        try:
            sess = self._db.get_active_session()
        except Exception:
            sess = None

        if not sess or sess["ea"] is not None:
            if self._initialized and self._prev_was_online:
                self._bus.emit("offline", {"source": "db"})
            self._initialized = True
            return

        sid = sess["id"]
        max_id = self._db_max_msg_id(sid)
        tcc = sess.get("tcc", 0)

        if not self._initialized:
            self._prev_max_id = max_id
            self._prev_tool_count = tcc
            self._initialized = True
            self._bus.emit("session_start", {"source": "db"})
            return

        # ── max_id 增长 → 新消息写入 ──
        if max_id > self._prev_max_id:
            self._emit_new_msg_events(sid, self._prev_max_id, max_id)

        # ── tool_count 增长 → 工具调用 ──
        if tcc > self._prev_tool_count:
            self._bus.emit("tool_end", {"source": "db"})  # turn 结束
            if self._prev_max_id < max_id:
                pass  # _emit_new_msg_events 已处理 tool_start
            else:
                pass
            # 因为 tool_count 和 max_id 同时更新（batch），
            # tool_start 由 _emit_new_msg_events 在新消息中检测

        self._prev_max_id = max_id
        self._prev_tool_count = tcc

    def _emit_new_msg_events(self, sid: str, from_id: int, to_id: int):
        """读取增量消息，为每条消息发射对应事件。"""
        try:
            self._db._ensure()
            rows = self._db._conn.execute(
                """SELECT id, role, tool_name, tool_calls
                   FROM messages WHERE session_id = ? AND id > ? AND id <= ?
                   ORDER BY id""",
                (sid, from_id, to_id),
            ).fetchall()
        except Exception:
            return

        for row in rows:
            msg_id, role, tn, tc_raw = row
            data = {"id": msg_id, "source": "db"}

            if role == "user":
                self._bus.emit("message_user", data)
                continue

            # 检查助理消息的工具调用
            if role == "assistant" and tc_raw and tc_raw.strip() not in ("", "[]", "{}"):
                try:
                    tc_list = json.loads(tc_raw)
                    if isinstance(tc_list, dict):
                        tc_list = [tc_list]
                    for tc in tc_list:
                        name = tc.get("function", {}).get("name", "") or tc.get("name", "")
                        if name and name.lower() == "clarify":
                            self._bus.emit("clarify_request", {"name": "clarify", "source": "db"})
                        elif name:
                            self._bus.emit("tool_start", {"name": name, "source": "db"})
                except Exception:
                    pass

            # 助理发送纯文本
            if role == "assistant" and (not tc_raw or tc_raw in ("", "[]", "{}")):
                self._bus.emit("message_assistant", data)

            # 工具返回
            if role == "tool":
                self._bus.emit("tool_end", {"name": tn or "?", "source": "db"})

    def _db_max_msg_id(self, sid: str) -> int:
        try:
            self._db._ensure()
            row = self._db._conn.execute(
                "SELECT MAX(id) FROM messages WHERE session_id = ?", (sid,)
            ).fetchone()
            return row[0] or 0
        except Exception:
            return 0


# 缓存 proc 检测结果（每 3 秒刷新一次）
_proc_cache: tuple[float, bool] = (0.0, False)

def _proc_present_check() -> bool:
    global _proc_cache
    now = time.time()
    if now - _proc_cache[0] > 3.0:
        try:
            p = ProcessDetector()
            present = p.present()
        except Exception:
            present = False
        _proc_cache = (now, present)
    return _proc_cache[1]


# ═══════════════════════════════════════════════════════════
#  图标绘制
# ═══════════════════════════════════════════════════════════

_LIT = {"red": QColor("#ff3b30"), "yellow": QColor("#ffcc00"), "green": QColor("#34c759")}
_DIM = {"red": QColor("#3a0a0a"), "yellow": QColor("#3a2e00"), "green": QColor("#0a2a0a")}


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
    status_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._db = StateDB()
        self._bus = HermesEventBus()
        self._fsm = EventFSM(self._bus)
        self._source = DbEventSource(self._bus, self._db)
        self._proc = ProcessDetector()

    def start(self):
        # 事件 → GUI 信号桥接
        def on_state_change(_data=None):
            prev = PollWorker._latest_fsm
            PollWorker._latest_fsm = self._fsm.state
            PollWorker._latest_light = self._fsm.light
            if prev != self._fsm.state:
                log.info("GUI ← %s (%s)", self._fsm.state.name, self._fsm.light)
            self.status_changed.emit(self._fsm.state)

        for ev in ("tool_start", "tool_end", "clarify_request",
                   "message_user", "message_assistant",
                   "session_start", "session_end",
                   "offline", "online",
                   "busy", "idle", "needs_input"):
            self._bus.on(ev, on_state_change)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(200)
        log.info("事件源已启动 (间隔 200ms)")

    def _tick(self):
        """每次 tick：先消费外部 UDP 事件，再 poll DB。"""
        # 1. 消费外部实时事件（来自 Hermes Plugin）
        while not _external_event_queue.empty():
            try:
                payload = _external_event_queue.get_nowait()
                ev = payload.get("event", "")
                data = {k: v for k, v in payload.items() if k != "event"}
                # 直接注入事件总线（实时）
                self._bus.emit(ev, data)
            except queue.Empty:
                break

        # 2. 仍从 DB poll 增量（兜底，捕获 plugin 漏掉的事件）
        try:
            self._source.tick()
        except Exception as e:
            log.error("DB 事件源异常: %s", e)

    def stop(self):
        self._timer.stop()
        self._db.close()

    _latest_fsm = FsmState.IDLE
    _latest_light = "green"

    @classmethod
    def current_state(cls) -> dict:
        return {
            "state": cls._latest_light,
            "timestamp": time.strftime("%H:%M:%S"),
            "label": FSM_LABELS.get(cls._latest_fsm, "🟢 空闲"),
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

        # ── 语言切换子菜单 ──
        self._lang_menu = m.addMenu("🌐 Language")
        self._lang_actions = {}
        for code, name in [("cn", "中文"), ("en", "English"), ("jp", "日本語"), ("kr", "한국어")]:
            a = QAction(name, self._lang_menu, checkable=True)
            a.setChecked(code == _LANG)
            a.triggered.connect(lambda checked, c=code: self._set_lang_tray(c))
            self._lang_menu.addAction(a)
            self._lang_actions[code] = a

        m.addSeparator()

        self._a_autostart = QAction("🔌 开机自启", checkable=True)
        self._a_autostart.setChecked(_is_autostart_enabled())
        self._a_autostart.triggered.connect(self._toggle_autostart)
        m.addAction(self._a_autostart)

        m.addSeparator()
        a_quit = m.addAction("退出")
        a_quit.triggered.connect(self.quit)
        self._tray.setContextMenu(m)

        self._last_fsm: Optional[FsmState] = None
        self._blink_on = True  # blink toggle state
        self._worker_ref: Optional[PollWorker] = None

        # ── 闪烁定时器 ──
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_timer.start(200)  # 基础 tick 200ms

        # ── HTTP 外部事件接收器（UI Observer → HTTP POST → 事件总线） ──
        self._http_thread = threading.Thread(
            target=start_http_receiver, daemon=True,
        )
        self._http_thread.start()

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

    def _set_lang_tray(self, code: str):
        """切换语言并更新菜单勾选状态。"""
        _set_lang(code)
        for c, a in self._lang_actions.items():
            a.setChecked(c == code)
        log.info("语言已切换 → %s", code.upper())

    def _toggle_autostart(self, checked: bool):
        """切换开机自启。"""
        result = _toggle_autostart(checked)
        self._a_autostart.setChecked(result)
        log.info("开机自启: %s", "启用" if result else "禁用")

    def _blink_tick(self):
        """每 200ms 触发，根据 FSM 状态决定图标闪烁。"""
        fsm = self._last_fsm or FsmState.IDLE
        light = FSM_TO_LIGHT.get(fsm, "green")
        interval = FSM_BLINK.get(fsm, 0)
        if interval == 0:
            # 不闪烁 → 常亮
            self._tray.setIcon(self._icons.get(light, self._icons["green"]))
            return

        # 闪烁: 每 blink_interval/200 次 tick 切换
        tick_mod = max(1, interval // 200)
        if not hasattr(self, '_blink_counter'):
            self._blink_counter = 0
        self._blink_counter += 1
        if self._blink_counter % tick_mod == 0:
            self._blink_on = not self._blink_on

        if self._blink_on:
            self._tray.setIcon(self._icons.get(light, self._icons["green"]))
        else:
            self._tray.setIcon(self._icons_dim.get(light, self._icons_dim["green"]))

    def _on_status(self, fsm: FsmState):
        """主线程接收 FSM 状态更新。"""
        if fsm == self._last_fsm:
            return
        self._last_fsm = fsm
        self._blink_on = True
        self._blink_counter = 0

        light = FSM_TO_LIGHT.get(fsm, "green")
        self._tray.setIcon(self._icons.get(light, self._icons["green"]))
        self._info.setText(f"状态: {FSM_LABELS.get(fsm, '未知')}")
        self._tray.setToolTip(FSM_TIPS.get(fsm, "Hermes Traffic Light"))
        log.info("FSM → %s (%s)", fsm.name, FSM_LABELS.get(fsm, ""))

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

    # 自动注入 Hermes UI Observer（无需手动 F12）
    _ensure_auto_injection()

    try:
        app = TrafficLightApp(sys.argv)
        sys.exit(app.exec())
    except Exception as e:
        log.error("致命错误: %s", e)
        import traceback
        log.error(traceback.format_exc())
        sys.exit(1)


def _ensure_auto_injection():
    """将 UI Observer 注入到 Hermes 的 index.html 中，实现自动加载。

    每次启动时检查并注入，即使 Hermes 更新后重置了 index.html，
    下次启动信号灯时会自动重新注入。
    """
    hermes_assets = Path(
        os.environ.get("LOCALAPPDATA", "C:/Users/Administrator/AppData/Local")
    ) / "hermes" / "hermes-agent" / "apps" / "desktop" / "release" / "win-unpacked" / "resources" / "app.asar.unpacked" / "dist" / "assets"

    hermes_html = hermes_assets.parent / "index.html"

    if not hermes_html.exists():
        log.info("Hermes 未安装或路径变更，跳过自动注入")
        return

    observer_dst = hermes_assets / "hermes-tl-observer.js"
    observer_src = APP_DIR / "inject-ui-observer.js"

    # 1. 复制 observer JS
    if observer_src.exists():
        try:
            import shutil
            shutil.copy2(str(observer_src), str(observer_dst))
            log.info("已注入 JS: %s", observer_dst)
        except Exception as e:
            log.warning("注入 JS 失败: %s", e)
    elif not observer_dst.exists():
        log.warning("observer JS 不存在，跳过注入")

    # 2. 检查 index.html 是否已有注入标记
    try:
        html = hermes_html.read_text(encoding="utf-8")
        if 'hermes-tl-observer.js' in html:
            log.info("index.html 已有注入标记")
            return

        # 在 </body> 前插入 script 标签
        html = html.replace("</body>", '    <script src="./assets/hermes-tl-observer.js"></script>\n  </body>')
        hermes_html.write_text(html, encoding="utf-8")
        log.info("已写入 index.html 注入标记")
    except Exception as e:
        log.warning("注入 index.html 失败: %s", e)


if __name__ == "__main__":
    main()
