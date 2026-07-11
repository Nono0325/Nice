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

# ── GPIO 引腳定義 (BCM 編號 - 升級為步進馬達配置) ──────────────────
PIN = {
    'X_PUL':      12,   # X 軸脈衝 (Row 3 - IO12)
    'X_DIR':      16,   # X 軸方向 (Row 2 - IO16)
    'X_ENA':      20,   # X 軸致能 (Row 3 - IO20)
    'Y_PUL':      13,   # Y 軸脈衝 (Row 4 - IO13)
    'Y_DIR':      19,   # Y 軸方向 (Row 3 - IO19)
    'Y_ENA':      26,   # Y 軸致能 (Row 4 - IO26)
    'VACUUM':     24,   # 吸盤繼電器 (Row 2 - IO24)
    'Z_DOWN':     25,   # 手臂下降繼電器 (Row 2 - IO25)
    'LIM_LEFT':   17,   # 限位開關-左 (Row 1 - IO17)
    'LIM_RIGHT':  27,   # 限位開關-右 (Row 4 - IO27)
    'LIM_UP':     22,   # 限位開關-上 (Row 3 - IO22)
    'LIM_DOWN':   23,   # 限位開關-下 (Row 3 - IO23)
}

# ── 步進馬達虛擬 PWM 規格 ──────────────────────────────────────────
# 保留原伺服的 500-2500us 概念，映射到步進馬達行程
PWM_FREQ     = 50       
PULSE_MIN    = 500      
PULSE_MAX    = 2500     
PULSE_CENTER = 1500     

def pulse_to_duty(pulse_us):
    """將脈衝寬度(µs)轉換成對應的 duty cycle，用於網頁顯示"""
    period_us = 1_000_000 / PWM_FREQ   # = 20000 µs
    return (pulse_us / period_us) * 100.0

# ── 系統狀態 ──────────────────────────────────────────────────────
state = {
    # 馬達當前位置 (對應 500~2500)
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

    # 範圍與物理比例設定
    'x_min': PULSE_MIN,
    'x_max': PULSE_MAX,
    'y_min': PULSE_MIN,
    'y_max': PULSE_MAX,
    'x_scale': 10.0,    # 10 µs 對應 1 mm (500~2500 行程 = 0~200 mm)
    'y_scale': 10.0,

    # 速度與加減速規劃
    'x_max_speed': 2000.0,
    'x_accel_steps': 100.0,
    'y_max_speed': 2000.0,
    'y_accel_steps': 100.0,

    # 致能狀態
    'motor_locked': True,

    # Y 軸同步模式
    'y_sync': True,

    # 最後更新時間
    'timestamp': '',
    'gpio_mode': 'Raspberry Pi (Real)' if IS_RASPBERRY_PI else 'Simulation',
}

# 歷史波形資料（供網頁繪圖）
MAX_HISTORY = 60
pwm_history = {
    'x':  [PULSE_CENTER] * MAX_HISTORY,
    'y1': [PULSE_CENTER] * MAX_HISTORY,
    'y2': [PULSE_CENTER] * MAX_HISTORY,
    'time': list(range(MAX_HISTORY)),
}

# ── 步進馬達背景控制類別 ──────────────────────────────────────────
class StepperMotor:
    def __init__(self, name, pul_pin, dir_pin, ena_pin):
        self.name = name
        self.pul_pin = pul_pin
        self.dir_pin = dir_pin
        self.ena_pin = ena_pin

        self.current_pos = float(PULSE_CENTER)
        self.target_pos = float(PULSE_CENTER)
        self.steps_per_unit = 5.0  # 1 us 單元對應 5 個步進脈衝
        
        # 速度規劃參數
        self.max_speed_hz = 2000.0
        self.min_speed_hz = 200.0
        self.accel_steps = 100.0
        self.current_speed_hz = 200.0
        
        self.enabled = True
        self.running = True
        
        if IS_RASPBERRY_PI:
            GPIO.setup(self.pul_pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.dir_pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self.ena_pin, GPIO.OUT, initial=GPIO.LOW) # 低電位使能

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def set_target(self, target):
        self.target_pos = max(500.0, min(2500.0, float(target)))

    def set_position(self, pos):
        self.current_pos = float(pos)
        self.target_pos = float(pos)

    def set_enable(self, value):
        self.enabled = value
        if IS_RASPBERRY_PI:
            # 共陰極接線下，ENA- 接地，ENA+ (GPIO) 輸出 LOW 鎖定馬達，輸出 HIGH 釋放馬達手推
            GPIO.output(self.ena_pin, GPIO.LOW if value else GPIO.HIGH)

    def _run(self):
        while self.running:
            if not self.enabled:
                time.sleep(0.01)
                continue

            diff = self.target_pos - self.current_pos
            step_val = 1.0 / self.steps_per_unit
            dist_steps = abs(diff) * self.steps_per_unit
            
            if dist_steps >= 1.0:
                # 梯形加減速規劃
                if dist_steps < self.accel_steps:
                    # 減速區
                    speed = self.min_speed_hz + (self.max_speed_hz - self.min_speed_hz) * (dist_steps / self.accel_steps)
                else:
                    # 加速區
                    speed = min(self.max_speed_hz, self.current_speed_hz + (self.max_speed_hz - self.min_speed_hz) / self.accel_steps)
                
                self.current_speed_hz = max(self.min_speed_hz, min(self.max_speed_hz, speed))
                
                if not IS_RASPBERRY_PI:
                    # 模擬模式：平滑移動
                    time.sleep(1.0 / self.current_speed_hz)
                    if diff > 0:
                        self.current_pos += step_val
                    else:
                        self.current_pos -= step_val
                    continue

                # 實際樹梅派模式
                direction = GPIO.HIGH if diff > 0 else GPIO.LOW
                GPIO.output(self.dir_pin, direction)
                
                # 限位開關安全防護
                if direction == GPIO.LOW and self.name == 'x' and state['lim_left']:
                    self.target_pos = self.current_pos
                    time.sleep(0.01)
                    continue
                if direction == GPIO.HIGH and self.name == 'x' and state['lim_right']:
                    self.target_pos = self.current_pos
                    time.sleep(0.01)
                    continue
                if direction == GPIO.LOW and self.name == 'y' and state['lim_down']:
                    self.target_pos = self.current_pos
                    time.sleep(0.01)
                    continue
                if direction == GPIO.HIGH and self.name == 'y' and state['lim_up']:
                    self.target_pos = self.current_pos
                    time.sleep(0.01)
                    continue

                # 發送步進脈衝
                GPIO.output(self.pul_pin, GPIO.HIGH)
                time.sleep(1.0 / (2.0 * self.current_speed_hz))
                GPIO.output(self.pul_pin, GPIO.LOW)
                time.sleep(1.0 / (2.0 * self.current_speed_hz))

                if diff > 0:
                    self.current_pos += step_val
                else:
                    self.current_pos -= step_val
            else:
                self.current_speed_hz = self.min_speed_hz
                time.sleep(0.005)

    def stop(self):
        self.running = False

# ── 步進馬達控制器物件 ─────────────────────────────────────────────
x_stepper = None
y_stepper = None

def init_gpio():
    """初始化 GPIO 引腳與步進馬達控制器"""
    global x_stepper, y_stepper
    
    # 建立/初始化步進馬達背景控制器
    if x_stepper is None:
        x_stepper = StepperMotor('x', PIN['X_PUL'], PIN['X_DIR'], PIN['X_ENA'])
    else:
        x_stepper.set_position(PULSE_CENTER)
        
    if y_stepper is None:
        y_stepper = StepperMotor('y', PIN['Y_PUL'], PIN['Y_DIR'], PIN['Y_ENA'])
    else:
        y_stepper.set_position(PULSE_CENTER)

    if not IS_RASPBERRY_PI:
        return

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

    print("[GPIO] Initialized stepper motor system successfully")

def cleanup_gpio():
    """清理 GPIO"""
    global x_stepper, y_stepper
    if x_stepper:
        x_stepper.stop()
    if y_stepper:
        y_stepper.stop()
    if not IS_RASPBERRY_PI:
        return
    GPIO.cleanup()

def set_servo_pulse(axis, pulse_us):
    """設定馬達目標位置"""
    pulse_us = max(PULSE_MIN, min(PULSE_MAX, pulse_us))

    if axis == 'x':
        if x_stepper:
            x_stepper.set_target(pulse_us)

    elif axis in ('y', 'y1', 'y2'):
        # 由於 Y1/Y2 同步或單一 Y 步進馬達，我們統一設定 y_stepper 的目標
        if y_stepper:
            y_stepper.set_target(pulse_us)

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
    global x_stepper, y_stepper
    if IS_RASPBERRY_PI:
        state['lim_left']  = not GPIO.input(PIN['LIM_LEFT'])   # PULLUP: 低電位=觸發
        state['lim_right'] = not GPIO.input(PIN['LIM_RIGHT'])
        state['lim_up']    = not GPIO.input(PIN['LIM_UP'])
        state['lim_down']  = not GPIO.input(PIN['LIM_DOWN'])
    else:
        # 模擬模式：根據位置自動模擬限位
        if x_stepper:
            state['lim_left']  = x_stepper.current_pos <= state['x_min'] + 10
            state['lim_right'] = x_stepper.current_pos >= state['x_max'] - 10
        if y_stepper:
            state['lim_down']  = y_stepper.current_pos <= state['y_min'] + 10
            state['lim_up']    = y_stepper.current_pos >= state['y_max'] - 10

def home_axis(axis='all'):
    """馬達歸零（回原點）"""
    global x_stepper, y_stepper
    
    if axis in ('x', 'all'):
        print("[HOME] X Axis homing...")
        if IS_RASPBERRY_PI and x_stepper:
            # 確保致能
            GPIO.output(x_stepper.ena_pin, GPIO.LOW)
            GPIO.output(x_stepper.dir_pin, GPIO.LOW) # 負方向向左
            
            while True:
                read_limit_switches()
                if state['lim_left']:
                    break
                # 發送單步脈衝
                GPIO.output(x_stepper.pul_pin, GPIO.HIGH)
                time.sleep(1.0 / (2.0 * x_stepper.speed_hz))
                GPIO.output(x_stepper.pul_pin, GPIO.LOW)
                time.sleep(1.0 / (2.0 * x_stepper.speed_hz))
            
            x_stepper.set_position(state['x_min'])
        else:
            if x_stepper:
                x_stepper.set_position(state['x_min'])
            time.sleep(0.5)
            
        if x_stepper:
            x_stepper.set_target(PULSE_CENTER)

    if axis in ('y', 'all'):
        print("[HOME] Y Axis homing...")
        if IS_RASPBERRY_PI and y_stepper:
            # 確保致能
            GPIO.output(y_stepper.ena_pin, GPIO.LOW)
            GPIO.output(y_stepper.dir_pin, GPIO.LOW) # 負方向向下
            
            while True:
                read_limit_switches()
                if state['lim_down']:
                    break
                # 發送單步脈衝
                GPIO.output(y_stepper.pul_pin, GPIO.HIGH)
                time.sleep(1.0 / (2.0 * y_stepper.speed_hz))
                GPIO.output(y_stepper.pul_pin, GPIO.LOW)
                time.sleep(1.0 / (2.0 * y_stepper.speed_hz))
            
            y_stepper.set_position(state['y_min'])
        else:
            if y_stepper:
                y_stepper.set_position(state['y_min'])
            time.sleep(0.5)
            
        if y_stepper:
            y_stepper.set_target(PULSE_CENTER)

# ── 背景廣播執行緒 ────────────────────────────────────────────────
broadcast_lock = threading.Lock()

def broadcast_state():
    """每 100ms 廣播狀態到所有客戶端"""
    global x_stepper, y_stepper
    sim_t = 0
    while True:
        try:
            # 同步實時馬達位置與百分比至系統狀態中
            if x_stepper:
                state['x_pulse'] = int(x_stepper.current_pos)
                state['x_pct'] = max(0.0, min(100.0, (x_stepper.current_pos - state['x_min']) / max(1, state['x_max'] - state['x_min']) * 100.0))
            if y_stepper:
                state['y1_pulse'] = int(y_stepper.current_pos)
                state['y2_pulse'] = int(y_stepper.current_pos)
                state['y_pct'] = max(0.0, min(100.0, (y_stepper.current_pos - state['y_min']) / max(1, state['y_max'] - state['y_min']) * 100.0))

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

# ── 操作歷史紀錄與巨集功能 ───────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history_log.json')
MACROS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'macros.json')

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history_list):
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save history: {e}")

def add_history(msg, type='info'):
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'time': time_str,
        'msg': msg,
        'type': type
    }
    history = load_history()
    history.append(log_entry)
    if len(history) > 500:
        history.pop(0)
    save_history(history)
    socketio.emit('new_history', log_entry)

def load_macros():
    if os.path.exists(MACROS_FILE):
        try:
            with open(MACROS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {
        '自動搬運範例': [
            '# 歸零與準備',
            'HOME',
            'DELAY 1000',
            '# 移動至取料點',
            'MOVE X 2000',
            'MOVE Y 1500',
            'DELAY 500',
            '# 下降並吸取',
            'ARM DOWN',
            'DELAY 1000',
            'VACUUM ON',
            'DELAY 500',
            'ARM UP',
            'DELAY 1000',
            '# 移動至放料點',
            'MOVE X 1000',
            'MOVE Y 1000',
            'DELAY 500',
            '# 下降並釋放',
            'ARM DOWN',
            'DELAY 1000',
            'VACUUM OFF',
            'DELAY 500',
            'ARM UP',
            'DELAY 1000',
            '# 完成並回原點',
            'HOME',
            'MSG 搬運任務已完成！'
        ]
    }

def save_macros(macros_dict):
    try:
        with open(MACROS_FILE, 'w', encoding='utf-8') as f:
            json.dump(macros_dict, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save macros: {e}")

macro_thread = None
macro_running = False
macro_paused = False

def run_macro_loop(commands):
    global macro_running, macro_paused
    macro_running = True
    macro_paused = False
    
    add_history("巨集執行開始", "success")
    socketio.emit('macro_status', {'running': True, 'paused': False, 'current_line': 0})
    
    idx = 0
    while idx < len(commands) and macro_running:
        if macro_paused:
            time.sleep(0.1)
            continue
            
        cmd = commands[idx].strip()
        idx += 1
        socketio.emit('macro_status', {'running': True, 'paused': False, 'current_line': idx})
        
        if not cmd or cmd.startswith('#') or cmd.startswith('//'):
            continue
            
        parts = cmd.split()
        op = parts[0].upper()
        
        if op == 'MOVE':
            if len(parts) >= 3:
                axis = parts[1].lower()
                try:
                    target = float(parts[2])
                    set_servo_pulse(axis, target)
                    add_history(f"巨集指令: 移動 {axis.upper()} 至 {target} µs", "info")
                    
                    while macro_running and not macro_paused:
                        if axis == 'x' and x_stepper:
                            if abs(x_stepper.current_pos - target) < 5:
                                break
                        elif axis in ('y', 'y1', 'y2') and y_stepper:
                            if abs(y_stepper.current_pos - target) < 5:
                                break
                        else:
                            break
                        time.sleep(0.05)
                except ValueError:
                    add_history(f"巨集錯誤: 無效的移動座標 '{parts[2]}'", "error")
            else:
                add_history("巨集錯誤: MOVE 指令參數不足", "error")
                
        elif op == 'DELAY':
            if len(parts) >= 2:
                try:
                    ms = float(parts[1])
                    add_history(f"巨集指令: 延遲 {ms} 毫秒", "info")
                    elapsed = 0.0
                    while elapsed < (ms / 1000.0) and macro_running:
                        if not macro_paused:
                            time.sleep(0.05)
                            elapsed += 0.05
                        else:
                            time.sleep(0.1)
                except ValueError:
                    add_history(f"巨集錯誤: 無效的延遲時間 '{parts[1]}'", "error")
            else:
                add_history("巨集錯誤: DELAY 指令參數不足", "error")
                
        elif op == 'VACUUM':
            if len(parts) >= 2:
                val = parts[1].upper() == 'ON'
                set_digital_output('vacuum', val)
                add_history(f"巨集指令: 吸盤 {'開啟' if val else '關閉'}", "info")
                time.sleep(0.5)
            else:
                add_history("巨集錯誤: VACUUM 指令參數不足", "error")
                
        elif op == 'ARM':
            if len(parts) >= 2:
                val = parts[1].upper() == 'DOWN'
                set_digital_output('z_down', val)
                add_history(f"巨集指令: 手臂 {'下降' if val else '上升'}", "info")
                time.sleep(0.5)
            else:
                add_history("巨集錯誤: ARM 指令參數不足", "error")
                
        elif op == 'HOME':
            axis = 'all'
            if len(parts) >= 2:
                axis = parts[1].lower()
            add_history(f"巨集指令: 馬達歸零 ({axis.upper()})", "info")
            home_axis(axis)
            time.sleep(1.0)
            
        elif op == 'MSG':
            msg = " ".join(parts[1:])
            add_history(f"巨集提示: {msg}", "success")
            socketio.emit('macro_msg', {'msg': msg})
            
        else:
            add_history(f"巨集錯誤: 未知指令 '{op}'", "error")
            
    macro_running = False
    socketio.emit('macro_status', {'running': False, 'paused': False, 'current_line': 0})
    add_history("巨集執行結束", "success")

# ── REST API ──────────────────────────────────────────────────────
@app.route('/api/start', methods=['POST'])
def api_start():
    state['system_run'] = True
    state['error'] = False
    state['error_msg'] = ''
    add_history("系統啟動", "success")
    return jsonify({'ok': True})

@app.route('/api/stop', methods=['POST'])
def api_stop():
    global macro_running
    state['system_run'] = False
    state['pickup_active'] = False
    macro_running = False
    add_history("系統停止", "warn")
    return jsonify({'ok': True})

@app.route('/api/home', methods=['POST'])
def api_home():
    data = request.get_json(silent=True) or {}
    axis = data.get('axis', 'all')
    add_history(f"手動點擊馬達歸零 ({axis.upper()})", "info")
    t = threading.Thread(target=home_axis, args=(axis,), daemon=True)
    t.start()
    return jsonify({'ok': True, 'msg': f'歸零中: {axis}'})

@app.route('/api/vacuum', methods=['POST'])
def api_vacuum():
    data = request.get_json(silent=True) or {}
    value = bool(data.get('on', False))
    set_digital_output('vacuum', value)
    add_history(f"手動切換吸盤: {'開啟' if value else '關閉'}", "info")
    return jsonify({'ok': True, 'vacuum': state['vacuum']})

@app.route('/api/z_down', methods=['POST'])
def api_z_down():
    data = request.get_json(silent=True) or {}
    value = bool(data.get('on', False))
    set_digital_output('z_down', value)
    state['arm_down'] = value
    add_history(f"手動切換手臂: {'下降' if value else '上升'}", "info")
    return jsonify({'ok': True, 'z_down': state['z_down']})

@app.route('/api/pickup', methods=['POST'])
def api_pickup():
    """自動取件流程"""
    if not state['system_run']:
        return jsonify({'ok': False, 'msg': '系統未啟動'})

    def pickup_sequence():
        state['pickup_active'] = True
        add_history("自動取件程序開始", "success")
        try:
            # 1. 移動到取件位置
            x_pickup = state['x_max'] - 200
            set_servo_pulse('x', x_pickup)
            time.sleep(0.8)
            # 2. 手臂下降
            set_digital_output('z_down', True)
            add_history("手臂下降中", "info")
            time.sleep(1.0)
            # 3. 吸盤啟動
            set_digital_output('vacuum', True)
            add_history("吸盤開啟並吸附工件", "info")
            time.sleep(0.5)
            # 4. 手臂上升
            set_digital_output('z_down', False)
            add_history("吸附成功，手臂上升", "info")
            time.sleep(0.8)
            # 5. X 移動到放置位置
            x_place = state['x_min'] + 200
            set_servo_pulse('x', x_place)
            time.sleep(0.8)
            # 6. 手臂下降
            set_digital_output('z_down', True)
            add_history("到達放料點，手臂下降", "info")
            time.sleep(0.8)
            # 7. 釋放吸盤
            set_digital_output('vacuum', False)
            add_history("吸盤關閉，工件已釋放", "info")
            time.sleep(0.5)
            # 8. 手臂上升
            set_digital_output('z_down', False)
            time.sleep(0.5)
            # 9. 回原點
            set_servo_pulse('x', PULSE_CENTER)
            time.sleep(0.5)
            add_history("自動取件程序完成，回到起點", "success")
        except Exception as e:
            state['error'] = True
            state['error_msg'] = str(e)
            add_history(f"自動取件異常: {e}", "error")
        finally:
            state['pickup_active'] = False

    t = threading.Thread(target=pickup_sequence, daemon=True)
    t.start()
    return jsonify({'ok': True, 'msg': '自動取件流程啟動'})

@app.route('/api/set_limits', methods=['POST'])
def api_set_limits():
    """設定馬達行程範圍與速度、校準參數"""
    data = request.get_json(silent=True) or {}
    if 'x_min' in data: state['x_min'] = max(PULSE_MIN, int(data['x_min']))
    if 'x_max' in data: state['x_max'] = min(PULSE_MAX, int(data['x_max']))
    if 'y_min' in data: state['y_min'] = max(PULSE_MIN, int(data['y_min']))
    if 'y_max' in data: state['y_max'] = min(PULSE_MAX, int(data['y_max']))
    if 'y_sync' in data: state['y_sync'] = bool(data['y_sync'])
    
    if 'x_max_speed' in data:
        state['x_max_speed'] = float(data['x_max_speed'])
        if x_stepper: x_stepper.max_speed_hz = float(data['x_max_speed'])
    if 'x_accel_steps' in data:
        state['x_accel_steps'] = float(data['x_accel_steps'])
        if x_stepper: x_stepper.accel_steps = float(data['x_accel_steps'])
    if 'y_max_speed' in data:
        state['y_max_speed'] = float(data['y_max_speed'])
        if y_stepper: y_stepper.max_speed_hz = float(data['y_max_speed'])
    if 'y_accel_steps' in data:
        state['y_accel_steps'] = float(data['y_accel_steps'])
        if y_stepper: y_stepper.accel_steps = float(data['y_accel_steps'])
        
    if 'x_scale' in data: state['x_scale'] = float(data['x_scale'])
    if 'y_scale' in data: state['y_scale'] = float(data['y_scale'])
    
    add_history("更新系統與馬達參數設定", "success")
    return jsonify({'ok': True, 'limits': {
        'x_min': state['x_min'], 'x_max': state['x_max'],
        'y_min': state['y_min'], 'y_max': state['y_max'],
        'y_sync': state['y_sync'],
        'x_max_speed': state['x_max_speed'], 'x_accel_steps': state['x_accel_steps'],
        'y_max_speed': state['y_max_speed'], 'y_accel_steps': state['y_accel_steps'],
        'x_scale': state['x_scale'], 'y_scale': state['y_scale']
    }})

@app.route('/api/macros', methods=['GET', 'POST', 'DELETE'])
def api_macros():
    if request.method == 'GET':
        return jsonify({'ok': True, 'macros': load_macros()})
    elif request.method == 'POST':
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        commands = data.get('commands')
        if not name or not isinstance(commands, list):
            return jsonify({'ok': False, 'msg': '無效的參數'})
        macros = load_macros()
        macros[name] = commands
        save_macros(macros)
        add_history(f"儲存巨集腳本: {name}", "success")
        return jsonify({'ok': True})
    elif request.method == 'DELETE':
        data = request.get_json(silent=True) or {}
        name = data.get('name')
        macros = load_macros()
        if name in macros:
            del macros[name]
            save_macros(macros)
            add_history(f"刪除巨集腳本: {name}", "warn")
            return jsonify({'ok': True})
        return jsonify({'ok': False, 'msg': '找不到該巨集'})

@app.route('/api/macro/run', methods=['POST'])
def api_macro_run():
    global macro_thread, macro_running, macro_paused
    data = request.get_json(silent=True) or {}
    action = data.get('action') # 'start', 'stop', 'pause', 'resume'
    name = data.get('name')
    
    if action == 'start':
        if macro_running:
            return jsonify({'ok': False, 'msg': '巨集已在運行中'})
        macros = load_macros()
        commands = macros.get(name)
        if not commands:
            return jsonify({'ok': False, 'msg': '找不到該巨集'})
        macro_thread = threading.Thread(target=run_macro_loop, args=(commands,), daemon=True)
        macro_thread.start()
        return jsonify({'ok': True})
        
    elif action == 'stop':
        macro_running = False
        macro_paused = False
        return jsonify({'ok': True})
        
    elif action == 'pause':
        macro_paused = True
        socketio.emit('macro_status', {'running': True, 'paused': True})
        return jsonify({'ok': True})
        
    elif action == 'resume':
        macro_paused = False
        socketio.emit('macro_status', {'running': True, 'paused': False})
        return jsonify({'ok': True})
        
    return jsonify({'ok': False, 'msg': '無效的指令'})

@app.route('/api/set_motor_enable', methods=['POST'])
def api_set_motor_enable():
    data = request.get_json(silent=True) or {}
    locked = bool(data.get('locked', True))
    state['motor_locked'] = locked
    
    if x_stepper:
        x_stepper.set_enable(locked)
    if y_stepper:
        y_stepper.set_enable(locked)
        
    status_str = "馬達鎖定 (致能通電中)" if locked else "馬達釋放 (斷電手推模式已啟用)"
    add_history(status_str, "warn")
    return jsonify({'ok': True, 'motor_locked': locked})

@app.route('/api/history', methods=['GET', 'DELETE'])
def api_history():
    if request.method == 'GET':
        return jsonify({'ok': True, 'history': load_history()})
    elif request.method == 'DELETE':
        save_history([])
        return jsonify({'ok': True})

@app.route('/api/diagnose')
def api_diagnose():
    """馬達診斷資訊"""
    diag = {
        'gpio_mode': state['gpio_mode'],
        'is_raspberry_pi': IS_RASPBERRY_PI,
        'pwm_freq': PWM_FREQ,
        'motors': {
            'X':  {'pin': PIN['X_PUL'],  'pulse': state['x_pulse'],  'duty': round(pulse_to_duty(state['x_pulse']), 3)},
            'Y1': {'pin': PIN['Y_PUL'], 'pulse': state['y1_pulse'], 'duty': round(pulse_to_duty(state['y1_pulse']), 3)},
            'Y2': {'pin': PIN['Y_PUL'], 'pulse': state['y2_pulse'], 'duty': round(pulse_to_duty(state['y2_pulse']), 3)},
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
    print("  樹梅派步進馬達控制系統 (已升級)")
    print("  Raspberry Pi Stepper Motor Controller")
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
