#!/usr/bin/env bash
# 直接執行 quick-install.sh
DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$DIR/quick-install.sh" ]; then
    bash "$DIR/quick-install.sh"
else
    curl -sSL https://raw.githubusercontent.com/Nono0325/Nice2/main/quick-install.sh | bash
fi
