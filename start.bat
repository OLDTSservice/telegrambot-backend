@echo off
chcp 65001 > nul
echo ========================================
echo  Telegram 機器人後台管理系統
echo ========================================
echo.

echo [1/2] 啟動後端 API 伺服器...
start "後端 API" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --reload --port 8000"

timeout /t 2 > nul

echo [2/2] 啟動前端開發伺服器...
start "前端" cmd /k "cd /d %~dp0frontend && npm install && npm run dev"

echo.
echo 後端 API：http://localhost:8000
echo 前端介面：http://localhost:5173
echo API 文件：http://localhost:8000/docs
echo.
echo 按任意鍵關閉此視窗（伺服器將繼續在背景運行）
pause > nul
