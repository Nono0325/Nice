#!/bin/bash
# ================================================================
# 璅寞?瘣曆撩?收??嗥頂蝯?- ???單
# ================================================================

echo "=================================================="
echo "  璅寞?瘣曆撩?收??嗥頂蝯?
echo "  Raspberry Pi Servo Motor Controller"
echo "=================================================="

# 瑼Ｘ?臬?冽邦璇晷銝?if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "[INFO] ?菜葫??Raspberry Pi 蝖祇?"
    echo "[INFO] ?? pigpio ??..."
    sudo pigpiod 2>/dev/null || true
    sleep 1
else
    echo "[INFO] ??Raspberry Pi ?啣?嚗蝙?冽芋?祆芋撘?
fi

# 撱箇???啣?嚗???摮嚗?if [ ! -d "venv" ]; then
    echo "[INFO] 撱箇? Python ??啣?..."
    python3 -m venv venv
fi

# ????啣?
source venv/bin/activate

# 摰?靘陷
echo "[INFO] 摰? Python 靘陷..."
pip install -q flask flask-socketio eventlet

# 憒??舀邦璇晷嚗?鋆?GPIO ?賢?摨?if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    pip install -q RPi.GPIO
fi

# ???祆? IP
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "[WEB] 隡箸??典??葉..."
echo "[WEB] ?砍閮芸?: http://localhost:5000"
echo "[WEB] ??雯頝? http://${IP}:5000"
echo ""

# ??隡箸???python3 servo_controller.py
