#!/usr/bin/env bash
# ==============================================================================
# 雙軸龍門控制系統一鍵安裝腳本 (樹梅派 Raspberry Pi 4 專用)
# ==============================================================================

set -e

CURRENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CURRENT_USER="$(whoami)"

echo "=== [1/4] 更新系統套件庫與安裝基礎相依性 ==="
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv curl

echo "=== [2/4] 安裝樹梅派 GPIO 硬體驅動 ==="
sudo apt-get install -y python3-rpi-lgpio 2>/dev/null || sudo apt-get install -y python3-rpi.gpio 2>/dev/null || true
sudo apt-get install -y python3-lgpio 2>/dev/null || true
sudo apt-get install -y pigpio python3-pigpio 2>/dev/null || true

echo "=== [3/4] 安裝 Python 核心驅動相依套件 ==="
cd "${CURRENT_DIR}"
if [ ! -d "venv" ]; then
    python3 -m venv venv --system-site-packages 2>/dev/null || true
fi

if [ -f "venv/bin/pip" ]; then
    venv/bin/pip install -r requirements.txt
    PYTHON_EXEC="${CURRENT_DIR}/venv/bin/python"
else
    pip3 install -r requirements.txt --break-system-packages 2>/dev/null || \
    pip3 install -r requirements.txt 2>/dev/null || \
    pip install -r requirements.txt 2>/dev/null || true
    PYTHON_EXEC=$(which python3 || echo "/usr/bin/python3")
fi

if command -v pigpiod &> /dev/null; then
    sudo systemctl enable pigpiod 2>/dev/null || true
    sudo systemctl restart pigpiod 2>/dev/null || true
fi

echo "=== [4/4] 註冊 systemd 自動開機啟動服務 ==="
SERVICE_FILE="/etc/systemd/system/gantry-control.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=雙軸龍門機械手臂智能控制系統守護行程
After=network.target
Wants=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=${PYTHON_EXEC} ${CURRENT_DIR}/main.py
Restart=always
RestartSec=3
KillMode=process
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable gantry-control.service
sudo systemctl restart gantry-control.service

sleep 2

IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$IP_ADDR" ] && IP_ADDR="127.0.0.1"

echo ""
echo "=========================================================="
echo " 安裝完成！控制系統已在後端背景持續運作！"
echo " 瀏覽器開啟控制頁面："
echo "   http://${IP_ADDR}:8000  或  http://localhost:8000"
echo "=========================================================="
