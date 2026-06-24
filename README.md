<div align="center">

# 🚦 Hermes Traffic Light

**系统托盘红绿灯 · 实时监控 Hermes Agent 工作状态**

[🇨🇳 中文](#-中文) · [🇬🇧 English](#-english) · [🇯🇵 日本語](#-日本語)

**✨ 闪烁动画 · 🌐 Web 界面 · 🔌 开机自启 · 📡 JSON API**

</div>

---

## 🇨🇳 中文

### 这是什么？

Hermes Traffic Light 是一个 **Windows 系统托盘红绿灯**，实时监控 [Hermes Agent](https://hermes-agent.nousresearch.com) 的工作状态。基于标准交通灯语义，一目了然：

| 颜色 | 状态 | 含义 |
|:---:|:---:|:---|
| 🔴 **红灯**（慢闪） | **正在执行** | Agent 正在调用工具、执行代码、处理任务 |
| 🟡 **黄灯**（快闪） | **等待用户** | Agent 在等待用户确认或输入（clarify 工具） |
| 🟢 **绿灯**（常亮） | **空闲** | 回答完毕，等待下一个任务 |
| ⚫ **灭灯** | **离线** | Hermes Desktop / CLI 未检测到 |

### 功能特性

- 🪟 **系统托盘图标** — 三色红绿灯，右键菜单一键操作
- 🌐 **Web 界面** — 浏览器打开 `http://127.0.0.1:19876`，带发光效果
- ✨ **闪烁动画** — 执行中红灯慢闪，等用户黄灯快闪，空闲常亮
- 📡 **JSON API** — `http://127.0.0.1:19876/state` 供第三方工具集成
- 🔌 **开机自启** — 右键菜单一键开关
- 🩺 **诊断工具** — `diagnose.py` 快速排查环境问题
- 📋 **详细日志** — `traffic_light.log` 记录每次状态变化

### 数据来源

| 来源 | 地址 | 用途 |
|------|------|------|
| **state.db** | `~/.hermes/state.db` | 读取最新会话消息、tool_calls 状态 |
| **API Server** | `http://127.0.0.1:8642/health/detailed` | 检测 active_agents 和 gateway_busy |
| **进程检测** | tasklist / hermes CLI / wmic | 确认 Hermes 是否在运行 |

三种检测方式互为兜底，确保判断准确。

### 判断逻辑

```
API Server busy?                    → 🔴 红灯
Hermes 未运行?                       → 🟢 绿灯（未工作 = 空闲）
无活跃会话?                          → 🟢 绿灯
最后消息: assistant + clarify?      → 🟡 黄灯
最后消息: assistant + 其他工具?     → 🔴 红灯
最后消息: tool / system?            → 🔴 红灯
最后消息: user 且 30s 内?           → 🔴 红灯
其他（回答完毕）                    → 🟢 绿灯
```

### 安装与使用

```bash
# 1. 安装依赖
pip install PyQt6

# 2. 启动
cd F:\JZT\Python\hermes_traffic_light
python traffic_light.py

# 或双击 start.bat
```

启动后出现在系统托盘，右键菜单：
- 🌐 在浏览器打开 → `http://127.0.0.1:19876`
- 🔄 强制刷新 → 清除进程检测缓存
- 🔌 开机自启 → 切换开机自动启动
- 退出 → 关闭程序

### 诊断

```bash
python diagnose.py
```

检查 state.db、API Server、Web 端口、进程状态等。

### 文件结构

```
hermes_traffic_light/
├── traffic_light.py     ← 主程序（系统托盘 + Web 服务器）
├── diagnose.py          ← 环境诊断工具
├── README.md            ← 本文档
├── start.bat            ← 快捷启动（后台静默）
├── start_interactive.bat    ← 带提示的交互式启动
├── diagnose.bat         ← 快速诊断
├── .gitignore
└── traffic_light.log    ← 运行日志（自动生成）
```

### 参考

本项目参考了 [hermes-status-light](https://github.com/1259764/hermes-status-light) 的 Web 界面和自动检测思路，结合 Windows 系统托盘和 state.db 精确判断进行了增强。

---

## 🇬🇧 English

### What is this?

**Hermes Traffic Light** is a **Windows system tray traffic light** that monitors the real-time working status of [Hermes Agent](https://hermes-agent.nousresearch.com). Standard traffic light semantics:

| Color | Status | Meaning |
|:---:|:---:|:---|
| 🔴 **Red** (slow blink) | **Working** | Agent is calling tools, executing code, processing |
| 🟡 **Yellow** (fast blink) | **Waiting** | Agent waiting for user confirmation (clarify tool) |
| 🟢 **Green** (steady) | **Idle** | Response complete, waiting for next task |
| ⚫ **Off** | **Offline** | Hermes Desktop / CLI not detected |

### Features

- 🪟 **System Tray Icon** — 3-color traffic light with right-click menu
- 🌐 **Web UI** — Open `http://127.0.0.1:19876` in browser with glow effects
- ✨ **Blink Animation** — Red slow-blink when working, yellow fast-blink when waiting, green steady when idle
- 📡 **JSON API** — `http://127.0.0.1:19876/state` for third-party integration
- 🔌 **Auto-start** — Toggle via right-click menu
- 🩺 **Diagnostic Tool** — `diagnose.py` for environment troubleshooting
- 📋 **Detailed Logging** — `traffic_light.log` records every state change

### Data Sources

| Source | Address | Purpose |
|--------|---------|---------|
| **state.db** | `~/.hermes/state.db` | Read latest session messages and tool_calls |
| **API Server** | `http://127.0.0.1:8642/health/detailed` | Detect active_agents and gateway_busy |
| **Process Detection** | tasklist / hermes CLI / wmic | Verify Hermes is running |

Three detection methods work together for accurate status.

### Logic

```
API Server busy?                    → 🔴 Red
Hermes not running?                 → 🟢 Green (not working = idle)
No active session?                  → 🟢 Green
Last msg: assistant + clarify?      → 🟡 Yellow
Last msg: assistant + other tools?  → 🔴 Red
Last msg: tool / system?            → 🔴 Red
Last msg: user within 30s?          → 🔴 Red
Other (response complete)           → 🟢 Green
```

### Installation

```bash
# 1. Install dependencies
pip install PyQt6

# 2. Run
cd F:\JZT\Python\hermes_traffic_light
python traffic_light.py

# Or double-click start.bat
```

Right-click the tray icon:
- 🌐 Open in Browser → `http://127.0.0.1:19876`
- 🔄 Force Refresh → Clear process detection cache
- 🔌 Auto-start → Toggle startup on boot
- Quit → Close

### Diagnostics

```bash
python diagnose.py
```

### File Structure

```
hermes_traffic_light/
├── traffic_light.py     ← Main program (tray + web server)
├── diagnose.py          ← Diagnostic tool
├── README.md            ← This file
├── start.bat            ← Quick launcher (silent)
├── start_interactive.bat    ← Launcher with prompt
├── diagnose.bat         ← Quick diagnostic
├── .gitignore
└── traffic_light.log    ← Runtime log (auto-generated)
```

### Reference

This project was inspired by [hermes-status-light](https://github.com/1259764/hermes-status-light)'s web UI and auto-detection approach, enhanced with Windows system tray and accurate state.db analysis.

---

## 🇯🇵 日本語

### これは何？

**Hermes Traffic Light** は [Hermes Agent](https://hermes-agent.nousresearch.com) の動作状態をリアルタイムに監視する **Windows タスクトレイ信号機**です。標準的な信号機の意味に従います：

| 色 | 状態 | 意味 |
|:---:|:---:|:---|
| 🔴 **赤**（低速点滅） | **実行中** | エージェントがツールを呼び出し、コードを実行中 |
| 🟡 **黄**（高速点滅） | **待機中** | ユーザーの確認・入力を待機中（clarify ツール） |
| 🟢 **緑**（常時点灯） | **待機中** | 応答完了、次のタスクを待機 |
| ⚫ **消灯** | **オフライン** | Hermes Desktop / CLI が検出されていません |

### 機能

- 🪟 **タスクトレイアイコン** — 3色信号機、右クリックメニュー
- 🌐 **Web インターフェース** — `http://127.0.0.1:19876` で発光エフェクト
- ✨ **点滅アニメーション** — 赤は低速点滅、黄は高速点滅、緑は常時点灯
- 📡 **JSON API** — `http://127.0.0.1:19876/state` で外部連携
- 🔌 **自動起動** — 右クリックメニューで切り替え
- 🩺 **診断ツール** — `diagnose.py` で環境確認
- 📋 **詳細ログ** — `traffic_light.log` に状態変化を記録

### データソース

| ソース | アドレス | 用途 |
|--------|---------|------|
| **state.db** | `~/.hermes/state.db` | 最新セッションのメッセージと tool_calls を読取 |
| **API Server** | `http://127.0.0.1:8642/health/detailed` | active_agents と gateway_busy を検出 |
| **プロセス検出** | tasklist / hermes CLI / wmic | Hermes の実行状態を確認 |

3つの検出方式が連携し、正確な状態判定を実現します。

### インストール

```bash
# 1. 依存関係のインストール
pip install PyQt6

# 2. 起動
cd F:\JZT\Python\hermes_traffic_light
python traffic_light.py

# または start.bat をダブルクリック
```

トレイアイコンを右クリック：
- 🌐 ブラウザで開く → `http://127.0.0.1:19876`
- 🔄 強制リフレッシュ → プロセス検出キャッシュをクリア
- 🔌 自動起動 → 起動時の自動開始を切替
- 終了 → プログラムを閉じる

### ファイル構成

```
hermes_traffic_light/
├── traffic_light.py     ← メインプログラム（トレイ + Web サーバー）
├── diagnose.py          ← 診断ツール
├── README.md            ← このファイル
├── start.bat            ← クイック起動（サイレント）
├── start_interactive.bat    ← 確認付き起動
├── diagnose.bat         ← クイック診断
├── .gitignore
└── traffic_light.log    ← 実行ログ（自動生成）
```

---

<div align="center">

**MIT License** · Made with ❤️ for the Hermes Agent community

[GitHub](https://github.com/Jiang/hermes-traffic-light) · [Report Issue](https://github.com/Jiang/hermes-traffic-light/issues)

</div>
