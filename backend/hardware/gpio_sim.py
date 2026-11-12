import logging
from typing import Dict
from .gpio_base import GPIOBase

logger = logging.getLogger("SimGPIO")

class SimGPIO(GPIOBase):
    """
    虛擬/模擬 GPIO 控制器。
    用於在開發環境 (Windows/Mac/非樹梅派Linux) 或測試模式下模擬馬達脈衝、電磁鐵與接近開關狀態。
    """
    def __init__(self):
        self.pin_modes: Dict[int, str] = {}    # "IN" or "OUT"
        self.pin_values: Dict[int, int] = {}   # 0 or 1
        self.pull_ups: Dict[int, bool] = {}
        logger.info("[模擬模式] 已啟動虛擬 GPIO 驅動器 (支援全功能模擬與虛擬感測器觸發)")

    def setup_pin_input(self, pin: int, pull_up: bool = True):
        self.pin_modes[pin] = "IN"
        self.pull_ups[pin] = pull_up
        # 預設上拉時為高電平 1 (未被感測器接地觸發)
        self.pin_values[pin] = 1 if pull_up else 0

    def setup_pin_output(self, pin: int, initial_state: int = 0):
        self.pin_modes[pin] = "OUT"
        self.pin_values[pin] = 1 if initial_state else 0

    def read_pin(self, pin: int) -> int:
        return self.pin_values.get(pin, 1 if self.pull_ups.get(pin, True) else 0)

    def write_pin(self, pin: int, value: int):
        self.pin_values[pin] = 1 if value else 0

    def set_sim_input(self, pin: int, value: int):
        """手動模擬或運動引擎注入感測器信號"""
        self.pin_values[pin] = 1 if value else 0

    def cleanup(self):
        self.pin_values.clear()
        self.pin_modes.clear()
        logger.info("[模擬模式] 虛擬 GPIO 資源已重置")

