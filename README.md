# Hermes Traffic Light 🚦

系统托盘红绿灯 + **Web 界面**，实时监控 Hermes Agent 的工作状态。

## 安装

确保已安装 PyQt6：

```bash
pip install PyQt6
```

## 使用

**方式一：双击运行**
直接双击 `traffic_light.py` 或 `start.bat`。

**方式二：命令行**
```bash
python traffic_light.py
```

启动后：

| 位置 | 说明 |
|------|------|
| 🪟 **系统托盘** | 红绿灯图标，右键菜单含"在浏览器打开" |
| 🌐 **Web 界面** | 浏览器访问 `http://127.0.0.1:19876`，发光红绿灯 + 自动刷新 |
| 📋 **JSON API** | `http://127.0.0.1:19876/state` 返回 `{"state":"green","timestamp":"...","label":"🟢 正在执行"}` |

## 状态含义

| 图标 | 状态 | 含义 |
|------|------|------|
| 🟢 绿灯 | 正在执行 | Hermes Agent 正在调用工具、执行代码、或处理任务 |
| 🟡 黄灯 | 等待用户 | Agent 已完成响应，正等待用户确认或输入（clarify 工具） |
| 🔴 红灯 | 空闲 | 无活动会话，会话已结束，或 Hermes 未运行 |
| ⚫ 灭灯 | 离线 | Hermes Desktop / CLI 未检测到 |

## 数据来源

1. **API Server**（`http://127.0.0.1:8642/health/detailed`）— 检测 `active_agents` 和 `gateway_busy`
2. **state.db**（`~/.hermes/state.db`）— 查询最新会话的消息角色和 tool_calls 状态
3. **进程检测** — tasklist / hermes CLI / wmic 确认 Hermes 是否在运行

## 判断逻辑

```
状态机: _determine_status()
  
  API Server busy?                → 🟢 绿灯
  Hermes 未运行?                   → 🔴 红灯
  无活跃会话?                      → 🔴 红灯
  最后消息: assistant + clarify?   → 🟡 黄灯
  最后消息: assistant + 其他工具?  → 🟢 绿灯
  最后消息: tool / system?         → 🟢 绿灯
  最后消息: user 且 30s 内?        → 🟢 绿灯
  其他?                            → 🔴 红灯
```

## Web 界面

浏览器打开 `http://127.0.0.1:19876` 即可查看带发光效果的红绿灯：

- 三盏大灯（红/黄/绿），高亮当前状态
- 自动轮询（500ms），无需手动刷新
- 背景跟随系统主题（深色）
- 页面标题实时更新

### JSON API

```bash
curl http://127.0.0.1:19876/state
# → {"state":"green","timestamp":"14:30:00","label":"🟢 正在执行"}
```

## 文件

| 文件 | 说明 |
|------|------|
| `traffic_light.py` | 主程序（系统托盘 + Web 服务器） |
| `diagnose.py` | 环境诊断工具 |
| `start.bat` | 快捷启动（后台静默） |
| `启动并暂停.bat` | 带提示和超时的启动 |
| `diagnose.bat` | 快速诊断批处理 |
| `traffic_light.log` | 运行日志（自动生成） |

## 参考

本项目参考了 [hermes-status-light](https://github.com/1259764/hermes-status-light) 的 Web 界面和自动检测思路，结合 Windows 系统托盘和 state.db 精确判断进行了增强。
