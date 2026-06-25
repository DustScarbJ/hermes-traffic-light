<div align="center">

# 🚦 Hermes Traffic Light

**系统托盘红绿灯 · 实时监控 Hermes Agent 工作状态**

[🇨🇳 中文](#-中文) · [🇬🇧 English](#-english) · [🇯🇵 日本語](#-日本語)

**✨ 实时事件驱动 · 🌐 Web 界面 · 🔌 开机自启 · 🧬 自动注入**

</div>

---

## 🇨🇳 中文

### 这是什么？

Hermes Traffic Light 是一个 **Windows 系统托盘红绿灯**，实时监控 [Hermes Agent](https://hermes-agent.nousresearch.com) 的工作状态。采用**三源事件驱动架构**，通过注入 Hermes 前端的 MutationObserver 实现真正实时的状态反馈：

| 颜色 | 状态 | 含义 |
|:---:|:---:|:---|
| 🟢 **绿灯**（常亮） | **正在运行** | Agent 正在执行任务 |
| 🟡 **黄灯**（慢闪） | **需要操作** | Agent 等待用户确认或输入 |
| 🔴 **红灯**（常亮） | **已停止** | 回答完毕，空闲中 |
| 🟡 **黄灯**（常亮） | **离线** | Hermes 未运行或无会话 |

### 功能特性

- 🪟 **系统托盘图标** — 四态红绿灯，右键菜单一键操作
- 🌐 **Web 界面** — 浏览器打开 `http://127.0.0.1:19876`，带发光效果
- ✨ **实时事件驱动** — 通过 MutationObserver 监听 Hermes UI 状态变化，零延迟
- 🧬 **自动注入** — 启动时自动将 Observer 注入 Hermes 前端，无需手动 F12
- 🛡️ **双源时钟锁** — UI 实时事件优先，DB 回放事件 2 秒免疫，杜绝状态覆盖
- 📡 **JSON API** — `http://127.0.0.1:19876/state` 供第三方工具集成
- 🔌 **开机自启** — 右键菜单一键开关
- 🩺 **诊断工具** — `diagnose.py` 快速排查环境问题
- 📋 **详细日志** — `traffic_light.log` 记录每次状态变化

### 架构

```
Hermes Desktop (Electron)
  └─ MutationObserver ──→ POST /event (fetch no-cors)
                              │
                         [HTTP :18888]
                              │
                    _external_event_queue
                              │
                    ┌─────────┴─────────┐
                    │  HermesEventBus   │
                    └────┬──────────┬───┘
                         │          │
                   [EventFSM]  [PollWorker → GUI]
                 双源时钟锁

Hermes Plugin (CLI/Gateway) ──→ UDP :18888 ──→ 同上
DbEventSource (DB poll 兜底)  ──→ source="db" 受免疫锁控制
```

### 安装与使用

```bash
# 1. 安装依赖
pip install PyQt6

# 2. 启动
cd hermes_traffic_light
python traffic_light.py

# 或双击 start.bat
```

启动后：
- 红绿灯图标出现在 **系统托盘**
- Observer 自动注入到 **Hermes 前端**
- 浏览器打开 `http://127.0.0.1:19876` 查看 Web 界面
- **无需任何手动操作**，红绿灯自动随 Hermes 状态变化

右键菜单：
- 🌐 **在浏览器打开** → `http://127.0.0.1:19876`
- 🔄 **强制刷新** → 清除进程检测缓存
- 🔌 **开机自启** → 切换开机自动启动
- **退出** → 关闭程序

### 技术说明

**三源事件驱动：**
| 来源 | 方式 | 延迟 | 用途 |
|------|------|:----:|------|
| UI Observer | MutationObserver → HTTP POST | 实时 | 主状态源 |
| Hermes Plugin | ctx.register_hook → UDP | 实时 | CLI/Gateway 模式 |
| DbEventSource | state.db 200ms 轮询 | Turn 级别 | 兜底 |

**双源时钟锁：**
- UI 事件到达后设置 2 秒免疫窗口
- 窗口内 DB 回放事件被自动丢弃
- 避免 turn 结束后 DB 批量回放覆盖实时状态

**自动注入：**
- 每次启动时检查 Hermes 的 `index.html`
- 自动添加 `hermes-tl-observer.js` 脚本引用
- Hermes 更新后自动重新注入

### 诊断

```bash
python diagnose.py
```

检查 state.db、Hermes 进程、Web 端口、Observer 注入状态等。

### 文件结构

```
hermes_traffic_light/
├── traffic_light.py          ← 主程序（托盘 + Web + 事件总线）
├── inject-ui-observer.js     ← Hermes UI MutationObserver 脚本
├── diagnose.py               ← 环境诊断工具
├── README.md                 ← 本文档
├── start.bat                 ← 快捷启动（后台静默）
├── start_interactive.bat     ← 带提示的交互式启动
├── diagnose.bat              ← 快速诊断
├── .gitignore
└── traffic_light.log         ← 运行日志（自动生成）
```

### License

MIT License · Made with ❤️ for the Hermes Agent community

---

## 🇬🇧 English

### What is this?

**Hermes Traffic Light** is a **Windows system tray traffic light** that monitors the real-time working status of [Hermes Agent](https://hermes-agent.nousresearch.com). Uses **3-source event-driven architecture** with a MutationObserver injected into Hermes' frontend for true real-time state feedback:

| Color | Status | Meaning |
|:---:|:---:|:---|
| 🟢 **Green** (steady) | **Running** | Agent is executing tasks |
| 🟡 **Yellow** (slow blink) | **Needs Input** | Agent waiting for user confirmation |
| 🔴 **Red** (steady) | **Stopped** | Idle, response complete |
| 🟡 **Yellow** (steady) | **Offline** | Hermes not running |

### Features

- 🪟 **System Tray Icon** — 4-state traffic light with context menu
- 🌐 **Web UI** — Open `http://127.0.0.1:19876` with glow effects
- ✨ **Real-time Event Driven** — MutationObserver monitors Hermes UI, zero latency
- 🧬 **Auto Injection** — Observer script auto-injected into Hermes frontend on startup
- 🛡️ **Dual-Source Clock Lock** — UI events prioritized, DB replay suppressed for 2s
- 📡 **JSON API** — `http://127.0.0.1:19876/state` for third-party integration
- 🔌 **Auto-start** — Toggle via right-click menu
- 🩺 **Diagnostics** — `diagnose.py` for environment troubleshooting
- 📋 **Detailed Logging** — `traffic_light.log` records every state change

### Architecture

```
Hermes Desktop (Electron)
  └─ MutationObserver ──→ POST /event (fetch no-cors)
                              │
                         [HTTP :18888]
                              │
                    _external_event_queue
                              │
                    ┌─────────┴─────────┐
                    │  HermesEventBus   │
                    └────┬──────────┬───┘
                         │          │
                   [EventFSM]  [PollWorker → GUI]
                Dual-Source Lock

Hermes Plugin (CLI/Gateway) ──→ UDP :18888
DbEventSource (DB poll fallback) ──→ source="db" immunity-locked
```

### Installation

```bash
# 1. Install dependencies
pip install PyQt6

# 2. Run
cd hermes_traffic_light
python traffic_light.py

# Or double-click start.bat
```

After launch:
- Traffic light appears in **system tray**
- Observer auto-injects into **Hermes frontend**
- Open `http://127.0.0.1:19876` in browser for Web UI
- **No manual setup needed** — lights follow Hermes automatically

### Data Sources

| Source | Method | Latency | Role |
|--------|--------|:-------:|------|
| UI Observer | MutationObserver → HTTP POST | Real-time | Primary |
| Hermes Plugin | ctx.register_hook → UDP | Real-time | CLI/Gateway |
| DbEventSource | state.db 200ms poll | Turn-level | Fallback |

### File Structure

```
hermes_traffic_light/
├── traffic_light.py          ← Main program
├── inject-ui-observer.js     ← Hermes UI MutationObserver script
├── diagnose.py               ← Diagnostic tool
├── README.md                 ← This file
├── start.bat                 ← Quick launcher
├── start_interactive.bat     ← Interactive launcher
├── diagnose.bat              ← Quick diagnostic
├── .gitignore
└── traffic_light.log         ← Runtime log
```

---

## 🇯🇵 日本語

### これは何？

**Hermes Traffic Light** は [Hermes Agent](https://hermes-agent.nousresearch.com) の動作状態をリアルタイムに監視する **Windows タスクトレイ信号機**です。**3ソースイベント駆動アーキテクチャ**を採用し、Hermes フロントエンドに注入された MutationObserver により真のリアルタイム状態フィードバックを実現：

| 色 | 状態 | 意味 |
|:---:|:---:|:---|
| 🟢 **緑**（常時点灯） | **実行中** | エージェントがタスクを実行中 |
| 🟡 **黄**（低速点滅） | **操作必要** | ユーザーの確認・入力を待機中 |
| 🔴 **赤**（常時点灯） | **停止中** | 応答完了、待機中 |
| 🟡 **黄**（常時点灯） | **オフライン** | Hermes が実行されていません |

### インストール

```bash
# 1. 依存関係のインストール
pip install PyQt6

# 2. 起動
cd hermes_traffic_light
python traffic_light.py
```

起動後：
- タスクトレイに信号機アイコンが表示
- Observer が Hermes フロントエンドに自動注入
- ブラウザで `http://127.0.0.1:19876` を開く
- **手動設定不要** — Hermes の状態に合わせて自動変化

### ファイル構成

```
hermes_traffic_light/
├── traffic_light.py          ← メインプログラム
├── inject-ui-observer.js     ← Hermes UI MutationObserver スクリプト
├── diagnose.py               ← 診断ツール
├── README.md                 ← このファイル
├── start.bat                 ← クイック起動
├── start_interactive.bat     ← 確認付き起動
├── diagnose.bat              ← クイック診断
├── .gitignore
└── traffic_light.log         ← 実行ログ
```

---

<div align="center">

**MIT License** · Made with ❤️ for the Hermes Agent community

[GitHub](https://github.com/DustScarbJ/hermes-traffic-light) · [Report Issue](https://github.com/DustScarbJ/hermes-traffic-light/issues)

</div>
