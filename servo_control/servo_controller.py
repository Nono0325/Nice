#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
樹梅派伺服馬達控制系統
Raspberry Pi Servo Motor Controller
=====================================
X 軸: 1 顆伺服馬達 (GPIO 12)
Y1 軸: 1 顆伺服馬達 (GPIO 13)
Y2 軸: 1 顆伺服馬達 (GPIO 18)
Z 軸 (上下): GPIO 繼電器 (GPIO 25)
吸盤 VACUUM: GPIO 繼電器 (GPIO 24)
限位開關: GPIO 17(左), 27(右), 22(上), 23(下)
"""

import os
import sys
import time
import math
import threading
import json
from datetime import datetime

# ── Flask / SocketIO ──────────────────────────────────────────────
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'servo_control_secret_2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── GPIO 模式偵測（非 Pi 環境使用 Mock） ───────────────────────────
IS_RASPBERRY_PI = False
try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    IS_RASPBERRY_PI = True
    print("[INFO] Running on Raspberry Pi - Real GPIO mode")
except (ImportError, RuntimeError):
    print("[INFO] Running in Simulation mode (not Raspberry Pi)")

# ── GPIO 引腳定義 (BCM 編號) ──────────────────────────────────────
PIN = {
    'X_SERVO':    12,   # X 軸伺服馬達 (Hardware PWM)
    'Y1_SERVO':   13,   # Y1 軸伺服馬達
    'Y2_SERVO':   18,   # Y2 軸伺服馬達
    'VACUUM':     24,   # 吸盤繼電器
    'Z_DOWN':     25,   # 手臂下降繼電器
    'LIM_LEFT':   17,   # 限位開關-左
    'LIM_RIGHT':  27,   # 限位開關-右
    'LIM_UP':     22,   # 限位開關-上
    'LIM_DOWN':   23,   # 限位開關-下
}

# ── PWM 規格 ──────────────────────────────────────────────────────
PWM_FREQ     = 50       # 50 Hz 標準伺服
PULSE_MIN    = 500      # µs - 最小脈衝寬度
PULSE_MAX    = 2500     # µs - 最大脈衝寬度
PULSE_CENTER = 1500     # µs - 中心點

def pulse_to_duty(pulse_us):
    """將脈衝寬度(µs)轉換成 RPi.GPIO duty cycle(%)"""
    period_us = 1_000_000 / PWM_FREQ   # = 20000 µs
    return (pulse_us / period_us) * 100.0

# ── 系統狀態 ──────────────────────────────────────────────────────
state = {
    # 馬達位置 (pulse width µs)
    'x_pulse':  PULSE_CENTER,
    'y1_pulse': PULSE_CENTER,
    'y2_pulse': PULSE_CENTER,

    # 轉換成百分比 0~100 (0=LEFT/DOWN, 100=RIGHT/UP)
    'x_pct':  50.0,
    'y_pct':  50.0,

    # 數位輸出
    'vacuum':   False,
    'z_down':   False,

    # 數位輸入（限位）
    'lim_left':  False,
    'lim_right': False,
    'lim_up':    False,
    'lim_down':  False,

    # 系統狀態
    'system_run':    False,
    'arm_down':      False,
    'pickup_active': False,
    'error':         False,
    'error_msg':     '',

    # 範圍設定 (µs)
    'x_min': PULSE_MIN,
    'x_max': PULSE_MAX,
    'y_min': PULSE_MIN,
    'y_max': PULSE_MAX,

    # Y 軸同步模式
    'y_sync': True,

    # 最後更新時間
    'timestamp': '',
    'gpio_mode': 'Raspberry Pi (Real)' if IS_RASPBERRY_PI else 'Simulation',
}

# PWM 歷史波形資料（供網頁繪圖）
MAX_HISTORY = 60
pwm_history = {
    'x':  [PULSE_CENTER] * MAX_HISTORY,
    'y1': [PULSE_CENTER] * MAX_HISTORY,
    'y2': [PULSE_CENTER] * MAX_HISTORY,
    'time': list(range(MAX_HISTORY)),
}

# ── GPIO / PWM 物件 ───────────────────────────────────────────────
pwm_objects = {}

def init_gpio():
    """初始化 GPIO 引腳與 PWM"""
    if not IS_RASPBERRY_PI:
        return

    # 伺服馬達輸出
    for pin_name in ['X_SERVO', 'Y1_SERVO', 'Y2_SERVO']:
        pin = PIN[pin_name]
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, PWM_FREQ)
        duty = pulse_to_duty(PULSE_CENTER)
        pwm.start(duty)
        pwm_objects[pin_name] = pwm

    # 數位輸出
    for pin_name in ['VACUUM', 'Z_DOWN']:
        GPIO.setup(PIN[pin_name], GPIO.OUT, initial=GPIO.LOW)

    # 數位輸入（限位開關）
    for pin_name in ['LIM_LEFT', 'LIM_RIGHT', 'LIM_UP', 'LIM_DOWN']:
        GPIO.setup(PIN[pin_name], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(
            PIN[pin_name], GPIO.BOTH,
            callback=lambda ch: read_limit_switches(),
            bouncetime=50
        )

    print("[GPIO] Initialized successfully")

def cleanup_gpio():
    """清理 GPIO"""
    if not IS_RASPBERRY_PI:
        return
    for pwm in pwm_objects.values():
        pwm.stop()
    GPIO.cleanup()

def set_servo_pulse(axis, pulse_us):
    """設定伺服馬達脈衝寬度"""
    pulse_us = max(PULSE_MIN, min(PULSE_MAX, pulse_us))

    if axis == 'x':
        state['x_pulse'] = pulse_us
        state['x_pct'] = (pulse_us - state['x_min']) / max(1, state['x_max'] - state['x_min']) * 100.0
        state['x_pct'] = max(0, min(100, state['x_pct']))
        if IS_RASPBERRY_PI and 'X_SERVO' in pwm_objects:
            pwm_objects['X_SERVO'].ChangeDutyCycle(pulse_to_duty(pulse_us))

    elif axis == 'y1':
        state['y1_pulse'] = pulse_us
        state['y_pct'] = (pulse_us - state['y_min']) / max(1, state['y_max'] - state['y_min']) * 100.0
        state['y_pct'] = max(0, min(100, state['y_pct']))
        if IS_RASPBERRY_PI and 'Y1_SERVO' in pwm_objects:
            pwm_objects['Y1_SERVO'].ChangeDutyCycle(pulse_to_duty(pulse_us))

    elif axis == 'y2':
        state['y2_pulse'] = pulse_us
        if IS_RASPBERRY_PI and 'Y2_SERVO' in pwm_objects:
            pwm_objects['Y2_SERVO'].ChangeDutyCycle(pulse_to_duty(pulse_us))

def set_digital_output(name, value):
    """設定數位輸出"""
    if name == 'vacuum':
        state['vacuum'] = value
        if IS_RASPBERRY_PI:
            GPIO.output(PIN['VACUUM'], GPIO.HIGH if value else GPIO.LOW)

    elif name == 'z_down':
        state['z_down'] = value
        state['arm_down'] = value
        if IS_RASPBERRY_PI:
            GPIO.output(PIN['Z_DOWN'], GPIO.HIGH if value else GPIO.LOW)

def read_limit_switches():
    """讀取所有限位開關"""
    if IS_RASPBERRY_PI:
        state['lim_left']  = not GPIO.input(PIN['LIM_LEFT'])   # PULLUP: 低電位=觸發
        state['lim_right'] = not GPIO.input(PIN['LIM_RIGHT'])
        state['lim_up']    = not GPIO.input(PIN['LIM_UP'])
        state['lim_down']  = not GPIO.input(PIN['LIM_DOWN'])
    else:
        # 模擬模式：根據位置自動模擬限位
        state['lim_left']  = state['x_pulse'] <= state['x_min'] + 10
        state['lim_right'] = state['x_pulse'] >= state['x_max'] - 10
        state['lim_up']    = state['y1_pulse'] >= state['y_max'] - 10
        state['lim_down']  = state['y1_pulse'] <= state['y_min'] + 10

def home_axis(axis='all'):
    """馬達歸零（回原點）"""
    if axis in ('x', 'all'):
        # X 軸往左移動直到觸發限位
        if IS_RASPBERRY_PI:
            target = state['x_min']
            current = state['x_pulse']
            step = -20
            while current > target:
                read_limit_switches()
                if state['lim_left']:
                    break
                current += step
                set_servo_pulse('x', current)
                time.sleep(0.02)
        set_servo_pulse('x', PULSE_CENTER)

    if axis in ('y', 'all'):
        if IS_RASPBERRY_PI:
            target = state['y_min']
            current = state['y1_pulse']
            step = -20
            while current > target:
                read_limit_switches()
                if state['lim_down']:
                    break
                current += step
                set_servo_pulse('y1', current)
                if state['y_sync']:
                    set_servo_pulse('y2', current)
                time.sleep(0.02)
        set_servo_pulse('y1', PULSE_CENTER)
        set_servo_pulse('y2', PULSE_CENTER)

# ── 背景廣播執行緒 ────────────────────────────────────────────────
broadcast_lock = threading.Lock()

def broadcast_state():
    """每 100ms 廣播狀態到所有客戶端"""
    sim_t = 0
    while True:
        try:
            read_limit_switches()
            state['timestamp'] = datetime.now().strftime('%H:%M:%S.%f')[:-3]

            # 模擬模式：產生輕微抖動效果（視覺用）
            if not IS_RASPBERRY_PI and state['system_run']:
                noise = math.sin(sim_t * 0.3) * 3
                sim_t += 0.1
            else:
                noise = 0
                sim_t += 0.1

            # 更新 PWM 歷史
            with broadcast_lock:
                pwm_history['x'].append(round(state['x_pulse'] + noise, 1))
                pwm_history['y1'].append(round(state['y1_pulse'] + noise * 0.8, 1))
                pwm_history['y2'].append(round(state['y2_pulse'] + noise * 0.6, 1))
                if len(pwm_history['x']) > MAX_HISTORY:
                    pwm_history['x'].pop(0)
                    pwm_history['y1'].pop(0)
                    pwm_history['y2'].pop(0)

            payload = {
                **state,
                'pwm_history': {
                    'x':  list(pwm_history['x']),
                    'y1': list(pwm_history['y1']),
                    'y2': list(pwm_history['y2']),
                },
                'pin_config': PIN,
            }
            socketio.emit('state_update', payload)

        except Exception as e:
            pass

        time.sleep(0.1)

# ── REST API ──────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    return jsonify({**state, 'pwm_history': pwm_history, 'pin_config': PIN})

@app.route('/api/move', methods=['POST'])
def api_move():
    data = request.get_json(silent=True) or {}
    axis   = data.get('axis', 'x')       # 'x', 'y1', 'y2', 'y'
    delta  = int(data.get('delta', 0))   # µs 增量
    target = data.get('target')           # 直接指定 µs

    if not state['system_run']:
        return jsonify({'ok': False, 'msg': '系統未啟動，請按 START'})

    try:
        if axis == 'x':
            new_pulse = state['x_pulse'] + delta if target is None else int(target)
            # 限位保護
            if state['lim_left'] and delta < 0:
                return jsonify({'ok': False, 'msg': 'X 軸左側限位'})
            if state['lim_right'] and delta > 0:
                return jsonify({'ok': False, 'msg': 'X 軸右側限位'})
            new_pulse = max(state['x_min'], min(state['x_max'], new_pulse))
            set_servo_pulse('x', new_pulse)

        elif axis in ('y', 'y1', 'y2'):
            new_pulse = state['y1_pulse'] + delta if target is None else int(target)
            if state['lim_up']   and delta > 0:
                return jsonify({'ok': False, 'msg': 'Y 軸上側限位'})
            if state['lim_down'] and delta < 0:
                return jsonify({'ok': False, 'msg': 'Y 軸下側限位'})
            new_pulse = max(state['y_min'], min(state['y_max'], new_pulse))
            set_servo_pulse('y1', new_pulse)
            if state['y_sync'] or axis == 'y':
                set_servo_pulse('y2', new_pulse)
            elif axis == 'y2':
                set_servo_pulse('y2', new_pulse)

        return jsonify({'ok': True, 'x_pulse': state['x_pulse'],
                        'y1_pulse': state['y1_pulse'], 'y2_pulse': state['y2_pulse']})
    except Exception as e:
        return jsonify({'ok': False, 'msg': str(e)})

@app.route('/api/set_position', methods=['POST'])
def api_set_position():
    """透過百分比 0~100 設定馬達位置"""
    data = request.get_json(silent=True) or {}
    axis = data.get('axis', 'x')
    pct  = float(data.get('pct', 50))

    if axis == 'x':
        pulse = state['x_min'] + (state['x_max'] - state['x_min']) * pct / 100
        set_servo_pulse('x', int(pulse))
    elif axis in ('y', 'y1'):
        pulse = state['y_min'] + (state['y_max'] - state['y_min']) * pct / 100
        set_servo_pulse('y1', int(pulse))
        if state['y_sync']:
            set_servo_pulse('y2', int(pulse))
    elif axis == 'y2':
        pulse = state['y_min'] + (state['y_max'] - state['y_min']) * pct / 100
        set_servo_pulse('y2', int(pulse))

    return jsonify({'ok': True})

@app.route('/api/start', methods=['POST'])
def api_start():
    state['system_run'] = True
    state['error'] = False
    state['error_msg'] = ''
    print("[SYS] System STARTED")
    return jsonify({'ok': True})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    state['system_run'] = False
    state['pickup_active'] = False
    print("[SYS] System STOPPED")
    return jsonify({'ok': True})

@app.route('/api/home', methods=['POST'])
def api_home():
    data = request.get_json(silent=True) or {}
    axis = data.get('axis', 'all')
    t = threading.Thread(target=home_axis, args=(axis,), daemon=True)
    t.start()
    return jsonify({'ok': True, 'msg': f'歸零中: {axis}'})

@app.route('/api/vacuum', methods=['POST'])
def api_vacuum():
    data = request.get_json(silent=True) or {}
    value = bool(data.get('on', False))
    set_digital_output('vacuum', value)
    return jsonify({'ok': True, 'vacuum': state['vacuum']})

@app.route('/api/z_down', methods=['POST'])
def api_z_down():
    data = request.get_json(silent=True) or {}
    value = bool(data.get('on', False))
    set_digital_output('z_down', value)
    state['arm_down'] = value
    return jsonify({'ok': True, 'z_down': state['z_down']})

@app.route('/api/pickup', methods=['POST'])
def api_pickup():
    """自動取件流程（仿照 PPT 工作流程）"""
    if not state['system_run']:
        return jsonify({'ok': False, 'msg': '系統未啟動'})

    def pickup_sequence():
        state['pickup_active'] = True
        try:
            # 1. 移動到取件位置（X 往右）
            x_pickup = state['x_max'] - 200
            set_servo_pulse('x', x_pickup)
            time.sleep(0.8)
            # 2. 手臂下降
            set_digital_output('z_down', True)
            time.sleep(1.0)
            # 3. 吸盤啟動
            set_digital_output('vacuum', True)
            time.sleep(0.5)
            # 4. 手臂上升
            set_digital_output('z_down', False)
            time.sleep(0.8)
            # 5. X 移動到放置位置
            x_place = state['x_min'] + 200
            set_servo_pulse('x', x_place)
            time.sleep(0.8)
            # 6. 手臂下降
            set_digital_output('z_down', True)
            time.sleep(0.8)
            # 7. 釋放吸盤
            set_digital_output('vacuum', False)
            time.sleep(0.5)
            # 8. 手臂上升
            set_digital_output('z_down', False)
            time.sleep(0.5)
            # 9. 回原點
            set_servo_pulse('x', PULSE_CENTER)
            time.sleep(0.5)
        except Exception as e:
            state['error'] = True
            state['error_msg'] = str(e)
        finally:
            state['pickup_active'] = False

    t = threading.Thread(target=pickup_sequence, daemon=True)
    t.start()
    return jsonify({'ok': True, 'msg': '自動取件流程啟動'})

@app.route('/api/set_limits', methods=['POST'])
def api_set_limits():
    """設定馬達行程範圍"""
    data = request.get_json(silent=True) or {}
    if 'x_min' in data:
        state['x_min'] = max(PULSE_MIN, int(data['x_min']))
    if 'x_max' in data:
        state['x_max'] = min(PULSE_MAX, int(data['x_max']))
    if 'y_min' in data:
        state['y_min'] = max(PULSE_MIN, int(data['y_min']))
    if 'y_max' in data:
        state['y_max'] = min(PULSE_MAX, int(data['y_max']))
    if 'y_sync' in data:
        state['y_sync'] = bool(data['y_sync'])
    return jsonify({'ok': True, 'limits': {
        'x_min': state['x_min'], 'x_max': state['x_max'],
        'y_min': state['y_min'], 'y_max': state['y_max'],
        'y_sync': state['y_sync']
    }})

@app.route('/api/diagnose')
def api_diagnose():
    """馬達診斷資訊"""
    diag = {
        'gpio_mode': state['gpio_mode'],
        'is_raspberry_pi': IS_RASPBERRY_PI,
        'pwm_freq': PWM_FREQ,
        'motors': {
            'X':  {'pin': PIN['X_SERVO'],  'pulse': state['x_pulse'],  'duty': round(pulse_to_duty(state['x_pulse']), 3)},
            'Y1': {'pin': PIN['Y1_SERVO'], 'pulse': state['y1_pulse'], 'duty': round(pulse_to_duty(state['y1_pulse']), 3)},
            'Y2': {'pin': PIN['Y2_SERVO'], 'pulse': state['y2_pulse'], 'duty': round(pulse_to_duty(state['y2_pulse']), 3)},
        },
        'digital_outputs': {
            'VACUUM': {'pin': PIN['VACUUM'], 'state': state['vacuum']},
            'Z_DOWN': {'pin': PIN['Z_DOWN'], 'state': state['z_down']},
        },
        'limit_switches': {
            'LEFT':  {'pin': PIN['LIM_LEFT'],  'triggered': state['lim_left']},
            'RIGHT': {'pin': PIN['LIM_RIGHT'], 'triggered': state['lim_right']},
            'UP':    {'pin': PIN['LIM_UP'],    'triggered': state['lim_up']},
            'DOWN':  {'pin': PIN['LIM_DOWN'],  'triggered': state['lim_down']},
        },
        'pwm_signal_info': {
            'frequency_hz': PWM_FREQ,
            'period_ms': round(1000 / PWM_FREQ, 2),
            'x_pulse_us':  state['x_pulse'],
            'y1_pulse_us': state['y1_pulse'],
            'y2_pulse_us': state['y2_pulse'],
            'x_duty_pct':  round(pulse_to_duty(state['x_pulse']), 3),
            'y1_duty_pct': round(pulse_to_duty(state['y1_pulse']), 3),
            'y2_duty_pct': round(pulse_to_duty(state['y2_pulse']), 3),
        }
    }
    return jsonify(diag)

# ── SocketIO 事件 ─────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    print(f"[WS] Client connected: {request.sid}")
    emit('state_update', {**state, 'pwm_history': pwm_history, 'pin_config': PIN})

@socketio.on('disconnect')
def on_disconnect():
    print(f"[WS] Client disconnected: {request.sid}")

@socketio.on('cmd_move')
def on_cmd_move(data):
    """WebSocket 移動命令（低延遲）"""
    axis  = data.get('axis', 'x')
    delta = int(data.get('delta', 0))
    if state['system_run']:
        with app.test_request_context():
            pass
        if axis == 'x':
            new_pulse = max(state['x_min'], min(state['x_max'], state['x_pulse'] + delta))
            set_servo_pulse('x', new_pulse)
        elif axis in ('y', 'y1'):
            new_pulse = max(state['y_min'], min(state['y_max'], state['y1_pulse'] + delta))
            set_servo_pulse('y1', new_pulse)
            if state['y_sync']:
                set_servo_pulse('y2', new_pulse)

# ── 主程式 ────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=" * 60)
    print("  樹梅派伺服馬達控制系統")
    print("  Raspberry Pi Servo Motor Controller")
    print(f"  模式: {state['gpio_mode']}")
    print("=" * 60)

    # 初始化 GPIO
    init_gpio()

    # 啟動廣播執行緒
    broadcast_thread = threading.Thread(target=broadcast_state, daemon=True)
    broadcast_thread.start()

    try:
        print("[WEB] Server starting at http://0.0.0.0:5000")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n[SYS] Shutting down...")
    finally:
        cleanup_gpio()
        print("[SYS] Bye!")
