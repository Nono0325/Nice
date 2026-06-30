#!/bin/bash
# ================================================================
#  樹梅派伺服馬達控制系統 - 一鍵安裝腳本
#  Raspberry Pi Servo Motor Controller - One-Click Installer
#
#  使用方式 / Usage:
#    curl -fsSL https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | bash
#  或 / or:
#    wget -qO- https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | bash
# ================================================================

set -e  # 遇到錯誤立即停止

# ── 顏色輸出 ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log_info()    { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()      { echo -e "${GREEN}[  OK]${NC}  $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
log_step()    { echo -e "\n${BOLD}${GREEN}▶ $1${NC}"; }

# ── 設定 ──────────────────────────────────────────────────────
REPO_URL="https://github.com/Nono0325/Nice.git"
INSTALL_DIR="/home/${SUDO_USER:-pi}/servo_control"
SERVICE_NAME="servo-control"
PYTHON_CMD="python3"
PORT=5000

# ── 標題橫幅 ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║       樹梅派伺服馬達控制系統 - 一鍵安裝             ║${NC}"
echo -e "${BOLD}${CYAN}║   Raspberry Pi Servo Motor Controller Installer      ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""

# ── 檢查 root 權限 ────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    log_warn "建議以 sudo 執行以設定 systemd 服務"
    log_warn "如只需執行程式（不自動開機），可直接執行"
fi

# ── 偵測系統 ─────────────────────────────────────────────────
log_step "偵測系統環境"

IS_PI=false
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null || grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    IS_PI=true
    PI_MODEL=$(cat /proc/cpuinfo | grep "Model" | head -1 | awk -F: '{print $2}' | xargs)
    log_ok "偵測到 Raspberry Pi: ${PI_MODEL}"
else
    log_warn "非 Raspberry Pi 環境，將使用模擬 GPIO 模式"
fi

OS_ID=$(cat /etc/os-release 2>/dev/null | grep "^ID=" | cut -d= -f2 | tr -d '"')
log_info "作業系統: ${OS_ID:-unknown}"

# ── 安裝系統依賴 ──────────────────────────────────────────────
log_step "安裝系統依賴"

if command -v apt-get &>/dev/null; then
    log_info "更新套件清單..."
    apt-get update -qq

    log_info "安裝 Python3 / pip / git..."
    apt-get install -y -qq python3 python3-pip python3-venv git curl 2>/dev/null

    if [ "$IS_PI" = true ]; then
        log_info "安裝樹梅派 GPIO 依賴..."
        apt-get install -y -qq python3-rpi.gpio pigpio python3-pigpio 2>/dev/null || true
    fi
    log_ok "系統依賴安裝完成"
else
    log_warn "非 apt 系統，跳過系統依賴安裝"
fi

# ── 克隆 / 更新程式碼 ─────────────────────────────────────────
log_step "取得程式碼"

if [ -d "$INSTALL_DIR" ]; then
    log_info "目錄已存在，更新中: ${INSTALL_DIR}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
    log_ok "程式碼已更新"
else
    log_info "克隆儲存庫: ${REPO_URL}"
    # 克隆完整 repo，然後複製 servo_control 目錄
    TMP_DIR=$(mktemp -d)
    git clone --depth=1 "$REPO_URL" "$TMP_DIR/repo"
    
    if [ -d "$TMP_DIR/repo/servo_control" ]; then
        cp -r "$TMP_DIR/repo/servo_control" "$INSTALL_DIR"
        log_ok "servo_control 目錄已安裝至: ${INSTALL_DIR}"
    else
        # 如果整個 repo 就是 servo_control
        cp -r "$TMP_DIR/repo" "$INSTALL_DIR"
        log_ok "程式碼已安裝至: ${INSTALL_DIR}"
    fi
    rm -rf "$TMP_DIR"
fi

cd "$INSTALL_DIR"

# ── 建立 Python 虛擬環境 ──────────────────────────────────────
log_step "建立 Python 虛擬環境"

if [ ! -d "$INSTALL_DIR/venv" ]; then
    $PYTHON_CMD -m venv "$INSTALL_DIR/venv"
    log_ok "虛擬環境建立完成"
else
    log_info "虛擬環境已存在"
fi

# 啟動虛擬環境
source "$INSTALL_DIR/venv/bin/activate"

# ── 安裝 Python 依賴 ──────────────────────────────────────────
log_step "安裝 Python 依賴"

pip install --upgrade pip -q
pip install flask flask-socketio eventlet -q

if [ "$IS_PI" = true ]; then
    log_info "安裝樹梅派 GPIO 函式庫..."
    pip install RPi.GPIO -q 2>/dev/null || log_warn "RPi.GPIO 安裝失敗，將使用模擬模式"
    pip install pigpio -q 2>/dev/null || true
fi

log_ok "Python 依賴安裝完成"

# ── 設定權限 ──────────────────────────────────────────────────
log_step "設定檔案權限"
chmod +x "$INSTALL_DIR/start.sh" 2>/dev/null || true
chown -R "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$INSTALL_DIR" 2>/dev/null || true
log_ok "權限設定完成"

# ── 設定 pigpio 服務（僅樹梅派）─────────────────────────────
if [ "$IS_PI" = true ] && [ "$EUID" -eq 0 ]; then
    log_step "設定 pigpio 服務"
    systemctl enable pigpiod 2>/dev/null || true
    systemctl start pigpiod 2>/dev/null || true
    log_ok "pigpio 服務已啟動"
fi

# ── 建立 systemd 服務（開機自動執行）────────────────────────
if [ "$EUID" -eq 0 ]; then
    log_step "設定開機自動執行 (systemd)"

    RUN_USER="${SUDO_USER:-pi}"

    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=樹梅派伺服馬達控制系統 (Servo Motor Controller)
Documentation=https://github.com/Nono0325/Nice
After=network.target pigpiod.service
Wants=network.target

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/servo_controller.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}.service
    systemctl start ${SERVICE_NAME}.service
    sleep 2

    if systemctl is-active --quiet ${SERVICE_NAME}; then
        log_ok "systemd 服務已啟動且設為開機自動執行"
    else
        log_warn "服務啟動失敗，請執行: sudo journalctl -u ${SERVICE_NAME} -n 20"
    fi
else
    log_warn "非 root 權限，跳過 systemd 設定"
    log_warn "如需開機自動執行，請以 sudo 重新執行此腳本"
fi

# ── 取得 IP 位址 ──────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
HOSTNAME=$(hostname 2>/dev/null)

# ── 完成 ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║              ✅  安裝完成！                          ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  📌 安裝目錄: ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  🌐 本機訪問: ${CYAN}http://localhost:${PORT}${NC}"
[ -n "$IP" ] && echo -e "  🌐 區域網路: ${CYAN}http://${IP}:${PORT}${NC}"
echo ""
echo -e "  ${BOLD}常用指令:${NC}"
echo -e "  手動啟動:     ${YELLOW}cd ${INSTALL_DIR} && ./start.sh${NC}"
if [ "$EUID" -eq 0 ]; then
    echo -e "  查看狀態:     ${YELLOW}sudo systemctl status ${SERVICE_NAME}${NC}"
    echo -e "  查看日誌:     ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
    echo -e "  停止服務:     ${YELLOW}sudo systemctl stop ${SERVICE_NAME}${NC}"
    echo -e "  重啟服務:     ${YELLOW}sudo systemctl restart ${SERVICE_NAME}${NC}"
    echo -e "  關閉自動啟動: ${YELLOW}sudo systemctl disable ${SERVICE_NAME}${NC}"
fi
echo ""
