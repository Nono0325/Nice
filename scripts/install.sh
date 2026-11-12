#!/usr/bin/env bash
# ==============================================================================
# 雙軸龍門控制系統一鍵安裝腳本 (樹梅派 Raspberry Pi 4 專用)
# ==============================================================================

set -e

echo "=== [1/5] 更新系統套件庫與安裝基礎相依性 ==="
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git pigpio python3-pigpio

echo "=== [2/5] 安裝 Python 核心驅動相依套件 ==="
# 若為 Raspberry Pi OS Bookworm (Debian 12)，使用 break-system-packages 或虛擬環境
pip3 install -r requirements.txt --break-system-packages || pip3 install -r requirements.txt

echo "=== [3/5] 啟用 pigpiod 守護行程 (高精度 DMA 脈衝) ==="
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "=== [4/5] 註冊 systemd 自動開機啟動服務 ==="
CURRENT_DIR=$(pwd)
CURRENT_USER=$(whoami)

# 動態產生符合當前路徑與使用者的 service 設定
sudo bash -c "cat <<EOF > /etc/systemd/system/gantry-control.service
[Unit]
Description=雙軸龍門機械手臂智能控制系統守護行程
After=network.target pigpiod.service

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=/usr/bin/python3 ${CURRENT_DIR}/main.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable gantry-control.service

echo "=== [5/5] 啟動控制服務 ==="
sudo systemctl restart gantry-control.service

IP_ADDR=$(hostname -I | awk '{print $1}')
echo ""
echo "=========================================================="
echo " 安裝完成！控制系統已在後端背景持續運作！"
echo " 瀏覽器開啟控制頁面："
echo "   http://${IP_ADDR}:8000  或  http://localhost:8000"
echo "=========================================================="

