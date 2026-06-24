@echo off
chcp 65001 >nul
echo ===== Hermes Traffic Light — 诊断工具 =====
echo.

echo 1. 检测 Python 环境和 PyQt6
python -c "import PyQt6; print('  PyQt6:', PyQt6.QtCore.PYQT_VERSION_STR)" 2>&1
python --version 2>&1
echo.

echo 2. 检测 Hermes 进程
tasklist /FI "IMAGENAME eq Hermes.exe" /NH 2>&1 | findstr /i Hermes
if %errorlevel% equ 0 (echo   ✅ Hermes.exe 运行中) else (echo   ❌ 未找到 Hermes.exe)
echo.

echo 3. 检测 hermes CLI
where hermes 2>nul && hermes --version 2>&1
if %errorlevel% equ 0 (echo   ✅ hermes CLI 可用) else (echo   ❌ hermes CLI 不可用)
echo.

echo 4. 检测 API Server (port 8642)
powershell -Command "& {try{$c=New-Object System.Net.Sockets.TcpClient;$c.Connect('127.0.0.1',8642);$c.Close();Write-Host '  ✅ API Server 端口开放'}catch{Write-Host '  ❌ API Server 未开放'}}"
echo.

echo 5. 检测 state.db
if exist "%USERPROFILE%\.hermes\state.db" (
    echo   ✅ state.db 存在
    dir "%USERPROFILE%\.hermes\state.db"
) else (
    echo   ❌ state.db 不存在
)
echo.

echo 6. 尝试直接连接 API Server
powershell -Command "& {try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:8642/health/detailed' -TimeoutSec 2;Write-Host ('  '+$r.Content)}catch{Write-Host '  ❌ 连接失败: '$_}}"
echo.

echo 7. 检测 Webhook Server (port 8644)
powershell -Command "& {try{$c=New-Object System.Net.Sockets.TcpClient;$c.Connect('127.0.0.1',8644);$c.Close();Write-Host '  ✅ Webhook 端口开放'}catch{Write-Host '  ❌ Webhook 未开放'}}"
echo.

echo ===== 诊断完成 =====
echo 如果状态都是❌，请确保 Hermes Desktop 正在运行。
echo 如需更精确的检测，请启用 API Server:
echo   hermes config set platforms.api_server.enabled true
echo   hermes gateway restart
pause
