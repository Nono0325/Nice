#!/usr/bin/env bash
# ==============================================================================
# 雙軸龍門機械手臂智能控制系統 - 一句指令極速全自動安裝與開機自啟
# 支援 Raspberry Pi OS Bookworm (Debian 12) & Bullseye (Debian 11)
# ==============================================================================

set -e

# 色彩輸出定義
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}   雙軸龍門機械手臂智能控制系統 (Raspberry Pi 4 專用)           ${NC}"
echo -e "${CYAN}   一鍵自動安裝 + 啟用開機自啟動 + 立即啟動運行                 ${NC}"
echo -e "${CYAN}================================================================${NC}"

# 1. 確保執行者身分
CURRENT_USER=$(whoami)
USER_HOME=$(eval echo "~${CURRENT_USER}")

if [ "$CURRENT_USER" = "root" ]; then
    echo -e "${YELLOW}提示: 檢測到以 root 身分執行${NC}"
    TARGET_DIR="${USER_HOME}/Nice2"
else
    TARGET_DIR="${USER_HOME}/Nice2"
fi

# 2. 檢測是否已位於專案目錄內
if [ -f "main.py" ] && [ -f "requirements.txt" ] && [ -d "backend" ]; then
    PROJECT_DIR=$(pwd)
    echo -e "${GREEN}✓ 檢測到已在專案目錄內: ${PROJECT_DIR}${NC}"
else
    PROJECT_DIR="${TARGET_DIR}"
    echo -e "${CYAN}>>> 正在檢查/安裝 Git...${NC}"
    if ! command -v git &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y git
    fi

    if [ -d "${PROJECT_DIR}/.git" ]; then
        echo -e "${CYAN}>>> 檢測到既有儲存庫，正在拉取最新程式碼...${NC}"
        cd "${PROJECT_DIR}"
        git pull || true
    else
        echo -e "${CYAN}>>> 正在下載最新專案程式碼至 ${PROJECT_DIR}...${NC}"
        git clone https://github.com/Nono0325/Nice2.git "${PROJECT_DIR}"
        cd "${PROJECT_DIR}"
    fi
fi

cd "${PROJECT_DIR}"

# 3. 安裝系統級基礎相依套件 (相容 Bookworm / Bullseye)
echo -e "${CYAN}>>> [1/4] 安裝 Linux 系統軟體套件與 GPIO 驅動...${NC}"
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv curl

# 針對 Bookworm 與 Bullseye 自動挑選最適合的 GPIO 驅動套件
echo -e "${CYAN}>>> 正在配置樹梅派 GPIO 硬體驅動程式...${NC}"
sudo apt-get install -y python3-rpi-lgpio 2>/dev/null || sudo apt-get install -y python3-rpi.gpio 2>/dev/null || true
sudo apt-get install -y python3-lgpio 2>/dev/null || true

# 若舊版系統提供 pigpio 則安裝，若新版 Bookworm 無此套件則自動跳過，不中斷安裝
sudo apt-get install -y pigpio python3-pigpio 2>/dev/null || true

# 4. 安裝 Python 核心驅動相依庫 (使用虛擬環境相容 Debian 12 PEP 668)
echo -e "${CYAN}>>> [2/4] 配置 Python 執行環境並安裝相依套件...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv --system-site-packages 2>/dev/null || true
fi

if [ -f "venv/bin/pip" ]; then
    echo -e "${CYAN}>>> 透過專用虛擬環境安裝相依套件...${NC}"
    venv/bin/pip install -r requirements.txt
    PYTHON_EXEC="${PROJECT_DIR}/venv/bin/python"
else
    echo -e "${CYAN}>>> 透過系統 pip 安裝相依套件...${NC}"
    pip3 install -r requirements.txt --break-system-packages 2>/dev/null || \
    pip3 install -r requirements.txt 2>/dev/null || \
    pip install -r requirements.txt 2>/dev/null || true
    PYTHON_EXEC=$(which python3 || echo "/usr/bin/python3")
fi

# 5. 若有安裝 pigpio 則啟用服務
if command -v pigpiod &> /dev/null; then
    echo -e "${CYAN}>>> [3/4] 啟用 pigpio 硬體定時 DMA 守護程序...${NC}"
    sudo systemctl enable pigpiod 2>/dev/null || true
    sudo systemctl restart pigpiod 2>/dev/null || true
else
    echo -e "${CYAN}>>> [3/4] 使用 Linux 核心 GPIO / lgpio 驅動模式 (相容 Bookworm)${NC}"
fi

# 6. 配置 systemd 開機自啟動服務
echo -e "${CYAN}>>> [4/4] 註冊並設定開機自啟動服務 (gantry-control.service)...${NC}"
SERVICE_FILE="/etc/systemd/system/gantry-control.service"

sudo bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=雙軸龍門機械手臂智能控制系統守護行程
After=network.target
Wants=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PYTHON_EXEC} ${PROJECT_DIR}/main.py
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

# 7. 取得本機 IP 並輸出完成訊息
IP_ADDR=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$IP_ADDR" ] && IP_ADDR="127.0.0.1"

echo ""
echo -e "${GREEN}================================================================${NC}"
echo -e "${GREEN}  🎉 安裝與啟動全部成功！${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "  ● 服務狀態:     ${GREEN}運行中 (Active: running)${NC}"
echo -e "  ● 開機自啟動:   ${GREEN}已啟用 (開機/斷電通電即自動運行)${NC}"
echo -e "  ● 專案路徑:     ${CYAN}${PROJECT_DIR}${NC}"
echo -e "  ● Python直譯器: ${CYAN}${PYTHON_EXEC}${NC}"
echo -e "  ● Web 控制頁面: ${YELLOW}http://${IP_ADDR}:8000${NC} 或 ${YELLOW}http://localhost:8000${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "常用指令說明："
echo -e "  檢視即時狀態:  ${CYAN}sudo systemctl status gantry-control${NC}"
echo -e "  即時運作日誌:  ${CYAN}sudo journalctl -u gantry-control -f${NC}"
echo -e "  重啟控制系統:  ${CYAN}sudo systemctl restart gantry-control${NC}"
echo -e "  停止控制系統:  ${CYAN}sudo systemctl stop gantry-control${NC}"
echo -e "${GREEN}================================================================${NC}"
