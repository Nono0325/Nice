#!/bin/bash
# ================================================================
# 樹梅派伺服馬達控制系統 - 啟動腳本
# ================================================================

echo "=================================================="
echo "  樹梅派伺服馬達控制系統"
echo "  Raspberry Pi Servo Motor Controller"
echo "=================================================="

# 檢查是否在樹梅派上
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "[INFO] 偵測到 Raspberry Pi 硬體"
    echo "[INFO] 啟動 pigpio 服務..."
    sudo pigpiod 2>/dev/null || true
    sleep 1
else
    echo "[INFO] 非 Raspberry Pi 環境，使用模擬模式"
fi

# 建立虛擬環境（如果不存在）
if [ ! -d "venv" ]; then
    echo "[INFO] 建立 Python 虛擬環境..."
    python3 -m venv venv
fi

# 啟動虛擬環境
source venv/bin/activate

# 安裝依賴
echo "[INFO] 安裝 Python 依賴..."
pip install -q flask flask-socketio eventlet

# 如果是樹梅派，安裝 GPIO 函式庫
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    pip install -q RPi.GPIO
fi

# 取得本機 IP
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "[WEB] 伺服器啟動中..."
echo "[WEB] 本地訪問: http://localhost:5000"
echo "[WEB] 區域網路: http://${IP}:5000"
echo ""

# 啟動伺服器
python3 servo_controller.py
