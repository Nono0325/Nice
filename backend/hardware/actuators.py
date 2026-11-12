import time
import threading
import logging
from typing import Dict, Any
from .gpio_base import GPIOBase
from ..config import ElectromagnetConfig, SensorPinConfig

logger = logging.getLogger("Actuators")

class ElectromagnetController:
    """
    控制 4 組 LSD-P25/20 圓形強力直流電磁鐵 (透過 PC817 光耦隔離驅動模組)
    """
    def __init__(self, gpio: GPIOBase, config: ElectromagnetConfig):
        self.gpio = gpio
        self.cfg = config
        self.pins = {
            1: self.cfg.em1_pin,
            2: self.cfg.em2_pin,
            3: self.cfg.em3_pin,
            4: self.cfg.em4_pin
        }
        self.states: Dict[int, bool] = {1: False, 2: False, 3: False, 4: False}
        self.turn_on_timestamps: Dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
        self._lock = threading.Lock()
        
        # 初始化輸出引腳 (初始關閉)
        for ch, pin in self.pins.items():
            init_val = 0 if self.cfg.active_high else 1
            self.gpio.setup_pin_output(pin, initial_state=init_val)

    def set_channel(self, channel: int, on: bool) -> bool:
        if channel not in self.pins:
            logger.error(f"無效的電磁鐵通道: {channel}")
            return False
        
        with self._lock:
            pin = self.pins[channel]
            val = 1 if (on if self.cfg.active_high else not on) else 0
            self.gpio.write_pin(pin, val)
            self.states[channel] = on
            if on:
                self.turn_on_timestamps[channel] = time.time()
            else:
                self.turn_on_timestamps[channel] = 0.0
            logger.info(f"電磁鐵 EM{channel} -> {'開啟 (吸附中)' if on else '關閉 (已斷電)'}")
            return True

    def set_all(self, on: bool):
        for ch in self.pins.keys():
            self.set_channel(ch, on)

    def get_states(self) -> Dict[str, Any]:
        with self._lock:
            # 檢查超時保護
            if self.cfg.auto_off_timeout_sec > 0:
                now = time.time()
                for ch, active in list(self.states.items()):
                    if active and (now - self.turn_on_timestamps[ch] > self.cfg.auto_off_timeout_sec):
                        logger.warning(f"電磁鐵 EM{ch} 通電超過安全時間 ({self.cfg.auto_off_timeout_sec}秒)，自動切斷以保護線圈！")
                        self.set_channel(ch, False)

            return {
                "em1": self.states[1],
                "em2": self.states[2],
                "em3": self.states[3],
                "em4": self.states[4],
                "any_active": any(self.states.values())
            }


class SensorMonitor:
    """
    監控 13 顆 QN-1805-E1 方形接近開關 (經 817 光耦隔離) 及 2 組 2HSS86H 驅動器報警信號
    X軸 3顆 (Left, Mid, Right)
    Z軸 2顆 (Up, Down)
    手臂末端 8顆 (Arm 1 ~ Arm 8)
    驅動器報警 2組 (X_ALM, Z_ALM)
    """
    def __init__(self, gpio: GPIOBase, config: SensorPinConfig):
        self.gpio = gpio
        self.cfg = config
        self.sensor_pins = {
            "x_left": self.cfg.x_left,
            "x_mid": self.cfg.x_mid,
            "x_right": self.cfg.x_right,
            "z_up": self.cfg.z_up,
            "z_down": self.cfg.z_down,
            "arm_1": self.cfg.arm_1,
            "arm_2": self.cfg.arm_2,
            "arm_3": self.cfg.arm_3,
            "arm_4": self.cfg.arm_4,
            "arm_5": self.cfg.arm_5,
            "arm_6": self.cfg.arm_6,
            "arm_7": self.cfg.arm_7,
            "arm_8": self.cfg.arm_8,
        }
        self.alarm_pins = {
            "x_alm": self.cfg.x_alm,
            "z_alm": self.cfg.z_alm
        }
        
        # 初始化輸入引腳並啟用內部上拉 (配合 817 光耦集電極開路接地輸出)
        for name, pin in self.sensor_pins.items():
            self.gpio.setup_pin_input(pin, pull_up=True)
            
        for name, pin in self.alarm_pins.items():
            if pin > 0:
                self.gpio.setup_pin_input(pin, pull_up=True)

    def read_all(self) -> Dict[str, Any]:
        results = {}
        # 接近開關讀取 (若 active_low=True，輸入為0代表金屬感應導通)
        for name, pin in self.sensor_pins.items():
            val = self.gpio.read_pin(pin)
            is_active = (val == 0) if self.cfg.active_low else (val == 1)
            results[name] = is_active
            
        # 驅動器警報讀取 (2HSS86H ALM 輸出通常故障時導通或斷開)
        for name, pin in self.alarm_pins.items():
            if pin > 0:
                val = self.gpio.read_pin(pin)
                # 驅動器正常時開路，報警時光耦導通 (LOW)
                results[name] = (val == 0)
            else:
                results[name] = False

        # 分組聚合方便前端展示
        results["summary"] = {
            "x_limits": {
                "left": results["x_left"],
                "mid": results["x_mid"],
                "right": results["x_right"]
            },
            "z_limits": {
                "up": results["z_up"],
                "down": results["z_down"]
            },
            "arm_sensors": [results[f"arm_{i}"] for i in range(1, 9)],
            "alarms": {
                "x_alm": results["x_alm"],
                "z_alm": results["z_alm"]
            }
        }
        return results

