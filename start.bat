@echo off
chcp 65001 >nul
REM Hermes Traffic Light — 启动脚本
cd /d "%~dp0"
echo 启动 Hermes Traffic Light…
echo   系统托盘: 红绿灯图标
echo   Web 界面: http://127.0.0.1:19876
echo.
start "" /b python traffic_light.py
echo 已启动。如需查看运行日志: traffic_light.log
