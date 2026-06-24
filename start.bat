@echo off
REM Hermes Traffic Light Launcher — v5 Web 增强版
cd /d "F:\JZT\Python\hermes_traffic_light"
echo 启动 Hermes Traffic Light…
echo 系统托盘: 红绿灯图标
echo Web 界面: http://127.0.0.1:19876
echo.
start /b python traffic_light.py
echo 已启动。如需查看运行日志: traffic_light.log
