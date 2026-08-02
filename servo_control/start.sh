#!/bin/bash
# ================================================================
# 樹梅派步進馬達控制系統 - 啟動腳本
# ================================================================

echo "=================================================="
echo "  樹梅派步進馬達控制系統"
echo "  Raspberry Pi Stepper Motor Controller"
echo "=================================================="

# 檢查是否在樹梅派上
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "[INFO] 偵測到 Raspberry Pi 硬體"
    echo "[INFO] 啟動 pigpio 服務..."
    sudo pigpiod 2>/dev/null || true
    sleep 1
else
    echo "[INFO] 非 Raspberry Pi 環境，使用虛擬模擬模式"
fi

# 建立虛擬環境（若不存在）
if [ ! -d "venv" ]; then
    echo "[INFO] 建立 Python 虛擬環境..."
    python3 -m venv venv
fi

# 啟動虛擬環境
source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null || true

# 安裝依賴
echo "[INFO] 檢查 Python 依賴套件..."
pip install -q flask flask-socketio eventlet

# 如果是樹梅派，安裝 GPIO 函式庫
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    pip install -q RPi.GPIO
fi

# 獲取本機 IP
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo ""
echo "[WEB] 伺服器啟動中..."
echo "[WEB] 本機位址: http://localhost:5000"
if [ -n "$IP" ]; then
    echo "[WEB] 區網位址: http://${IP}:5000"
fi
echo ""

# 啟動主程式
python3 servo_controller.py
