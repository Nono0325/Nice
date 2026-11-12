#!/usr/bin/env bash
# ==============================================================================
# (選用) 樹梅派螢幕全螢幕儀表板開機自啟 (Kiosk Mode)
# 適用於配備 7吋 / 10吋觸控螢幕或 HDMI 顯示器的機台
# ==============================================================================

set -e

AUTOSTART_DIR="$HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"

DESKTOP_FILE="$AUTOSTART_DIR/gantry-kiosk.desktop"

echo ">>> 正在建立桌面 Kiosk 全螢幕開機自啟項目: ${DESKTOP_FILE}..."

cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=Gantry Cockpit Kiosk
Comment=雙軸龍門機械手臂觸控主控台
Exec=chromium-browser --noerrdialogs --disable-infobars --kiosk --check-for-update-interval=31536000 http://localhost:8000
Terminal=false
EOF

chmod +x "$DESKTOP_FILE"

echo "=========================================================="
echo " Kiosk 螢幕自啟已設定完成！"
echo " 樹梅派進入桌面後將自動全螢幕開啟控制介面！"
echo "=========================================================="

