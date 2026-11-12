#!/usr/bin/env bash
# ==============================================================================
# 樹梅派開機自動啟動 (Auto-Start on Boot) 安裝與設定腳本
# ==============================================================================

set -e

SERVICE_NAME="gantry-control"
CURRENT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CURRENT_USER="$(whoami)"
PYTHON_BIN="$(which python3 || echo /usr/bin/python3)"

echo "=========================================================="
echo " 正在設定樹梅派開機自啟動服務: ${SERVICE_NAME}"
echo " 工作目錄: ${CURRENT_DIR}"
echo " 執行身分: ${CURRENT_USER}"
echo " Python 路徑: ${PYTHON_BIN}"
echo "=========================================================="

# 確保必要權限
if [ "$EUID" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 建立 systemd 服務單元檔
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo ">>> 正在寫入 systemd 服務檔: ${SERVICE_FILE}..."
$SUDO bash -c "cat <<EOF > ${SERVICE_FILE}
[Unit]
Description=雙軸龍門機械手臂智能控制系統守護行程
After=network.target pigpiod.service
Wants=network.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${CURRENT_DIR}
ExecStart=${PYTHON_BIN} ${CURRENT_DIR}/main.py
Restart=always
RestartSec=3
KillMode=process
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF"

echo ">>> 重新加載 systemd 設定檔..."
$SUDO systemctl daemon-reload

echo ">>> 啟用開機自啟動 (Enable)..."
$SUDO systemctl enable ${SERVICE_NAME}.service

echo ">>> 立即啟動服務..."
$SUDO systemctl restart ${SERVICE_NAME}.service

sleep 2

echo ">>> 檢查服務運作狀態:"
$SUDO systemctl status ${SERVICE_NAME}.service --no-pager

echo ""
echo "=========================================================="
echo " 樹梅派開機自啟動已設定完成！"
echo " 今後樹梅派只要通電開機，控制後端將自動在背景啟動！"
echo " 常用管理指令："
echo "   檢視狀態: sudo systemctl status ${SERVICE_NAME}"
echo "   重啟服務: sudo systemctl restart ${SERVICE_NAME}"
echo "   停止服務: sudo systemctl stop ${SERVICE_NAME}"
echo "   檢視日誌: sudo journalctl -u ${SERVICE_NAME} -f"
echo "=========================================================="

