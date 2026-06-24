@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Hermes Traffic Light — 启动中…
echo 如果启动后立即消失，请在命令行手动执行:
echo   python traffic_light.py
echo.
echo 先用诊断工具排查:
echo   diagnose.bat
echo.
echo 3 秒后启动程序…
timeout /t 3 /nobreak >nul
python traffic_light.py
echo.
echo 程序已退出 (错误码: %ERRORLEVEL%)
pause
