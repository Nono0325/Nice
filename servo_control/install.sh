#!/bin/bash
# ================================================================
#  Raspberry Pi Stepper Motor Controller - One-Click Installer
#
#  Usage:
#    curl -fsSL https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | sudo bash
#  or:
#    wget -qO- https://raw.githubusercontent.com/Nono0325/Nice/main/servo_control/install.sh | sudo bash
# ================================================================

set -e  # exit on error

# ── Color definitions ──────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log_info()  { echo -e "${CYAN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[  OK]${NC}  $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
log_step()  { echo -e "\n${BOLD}${GREEN}>>> $1${NC}"; }

# ── Configuration ──────────────────────────────────────────────
REPO_URL="https://github.com/Nono0325/Nice.git"
INSTALL_DIR="/home/${SUDO_USER:-pi}/servo_control"
SERVICE_NAME="servo-control"
PYTHON_CMD="python3"
PORT=5000

# ── Banner ─────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}========================================================${NC}"
echo -e "${BOLD}${CYAN}||   Raspberry Pi Stepper Motor Controller Installer  ||${NC}"
echo -e "${BOLD}${CYAN}========================================================${NC}"
echo ""

# ── Check for root / sudo ──────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    log_warn "Not running as root. systemd service setup will be skipped."
    log_warn "Re-run with sudo for full installation."
fi

# ── Detect platform ────────────────────────────────────────────
log_step "Detecting platform"

IS_PI=false
if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null || grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    IS_PI=true
    PI_MODEL=$(grep "Model" /proc/cpuinfo | head -1 | awk -F: '{print $2}' | xargs)
    log_ok "Detected Raspberry Pi: ${PI_MODEL}"
else
    log_warn "Not running on Raspberry Pi - GPIO features will be simulated."
fi

OS_ID=$(grep "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')
log_info "OS: ${OS_ID:-unknown}"

# ── Install system packages ────────────────────────────────────
log_step "Installing system packages"

if command -v apt-get &>/dev/null; then
    log_info "Updating package list..."
    apt-get update -qq

    log_info "Installing Python3 / pip / git..."
    apt-get install -y -qq python3 python3-pip python3-venv git curl 2>/dev/null

    if [ "$IS_PI" = true ]; then
        log_info "Installing Raspberry Pi GPIO libraries..."
        apt-get install -y -qq python3-rpi.gpio pigpio python3-pigpio 2>/dev/null || true
    fi
    log_ok "System packages installed"
else
    log_warn "apt not found - skipping system package installation"
fi

# ── Clone or update repository ────────────────────────────────
log_step "Cloning / updating repository"

if [ -d "$INSTALL_DIR" ]; then
    log_info "Directory exists, pulling latest: ${INSTALL_DIR}"
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || git pull origin master 2>/dev/null || true
    log_ok "Repository updated"
else
    log_info "Cloning from ${REPO_URL}"
    TMP_DIR=$(mktemp -d)
    git clone --depth=1 "$REPO_URL" "$TMP_DIR/repo"

    if [ -d "$TMP_DIR/repo/servo_control" ]; then
        cp -r "$TMP_DIR/repo/servo_control" "$INSTALL_DIR"
        log_ok "servo_control directory installed to: ${INSTALL_DIR}"
    else
        cp -r "$TMP_DIR/repo" "$INSTALL_DIR"
        log_ok "Repository installed to: ${INSTALL_DIR}"
    fi
    rm -rf "$TMP_DIR"
fi

cd "$INSTALL_DIR"

# ── Create Python virtual environment ─────────────────────────
log_step "Setting up Python virtual environment"

if [ ! -d "$INSTALL_DIR/venv" ]; then
    $PYTHON_CMD -m venv "$INSTALL_DIR/venv"
    log_ok "Virtual environment created"
else
    log_info "Virtual environment already exists"
fi

# Activate venv
source "$INSTALL_DIR/venv/bin/activate"

# ── Install Python dependencies ────────────────────────────────
log_step "Installing Python dependencies"

pip install --upgrade pip -q
pip install flask flask-socketio eventlet -q

if [ "$IS_PI" = true ]; then
    log_info "Installing Raspberry Pi GPIO Python packages..."
    pip install RPi.GPIO -q 2>/dev/null || log_warn "RPi.GPIO install failed - GPIO will be simulated"
    pip install pigpio -q 2>/dev/null || true
fi

log_ok "Python dependencies installed"

# ── Fix file permissions ───────────────────────────────────────
log_step "Setting file permissions"
chmod +x "$INSTALL_DIR/start.sh" 2>/dev/null || true
chown -R "${SUDO_USER:-pi}:${SUDO_USER:-pi}" "$INSTALL_DIR" 2>/dev/null || true
log_ok "Permissions set"

# ── Enable pigpiod service (Pi only) ──────────────────────────
if [ "$IS_PI" = true ] && [ "$EUID" -eq 0 ]; then
    log_step "Enabling pigpio daemon"
    systemctl enable pigpiod 2>/dev/null || true
    systemctl start pigpiod 2>/dev/null || true
    log_ok "pigpio daemon enabled"
fi

# ── Create and enable systemd service ────────────────────────
if [ "$EUID" -eq 0 ]; then
    log_step "Installing systemd service (auto-start on boot)"

    RUN_USER="${SUDO_USER:-pi}"

    # Configure NOPASSWD rule for Web Terminal commands
    echo "${RUN_USER} ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/servo-control
    chmod 0440 /etc/sudoers.d/servo-control

    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Raspberry Pi Stepper Motor Controller
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
        log_ok "systemd service started - auto-start enabled"
    else
        log_warn "Service may have failed. Check: sudo journalctl -u ${SERVICE_NAME} -n 20"
    fi
else
    log_warn "Not root - skipping systemd service installation"
    log_warn "To enable auto-start, re-run with sudo"
fi

# ── Print summary ──────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
HOSTNAME=$(hostname 2>/dev/null)

echo ""
echo -e "${BOLD}${GREEN}========================================================${NC}"
echo -e "${BOLD}${GREEN}||              Installation Complete!               ||${NC}"
echo -e "${BOLD}${GREEN}========================================================${NC}"
echo ""
echo -e "  Install directory : ${CYAN}${INSTALL_DIR}${NC}"
echo -e "  Local URL         : ${CYAN}http://localhost:${PORT}${NC}"
[ -n "$IP" ] && echo -e "  Network URL       : ${CYAN}http://${IP}:${PORT}${NC}"
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "  Manual start   : ${YELLOW}cd ${INSTALL_DIR} && ./start.sh${NC}"
if [ "$EUID" -eq 0 ]; then
    echo -e "  Service status : ${YELLOW}sudo systemctl status ${SERVICE_NAME}${NC}"
    echo -e "  Live logs      : ${YELLOW}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
    echo -e "  Stop service   : ${YELLOW}sudo systemctl stop ${SERVICE_NAME}${NC}"
    echo -e "  Restart        : ${YELLOW}sudo systemctl restart ${SERVICE_NAME}${NC}"
    echo -e "  Disable boot   : ${YELLOW}sudo systemctl disable ${SERVICE_NAME}${NC}"
fi
echo ""
