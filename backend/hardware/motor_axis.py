import time
import math
import threading
import logging
from typing import Optional, Callable
from .gpio_base import GPIOBase
from .gpio_sim import SimGPIO
from ..config import MotorConfig

logger = logging.getLogger("MotorAxis")

class MotorAxis:
    """
    閉環步進驅動器 (2HSS86H) 控制軸
    支援梯形加減速規劃、位置追蹤、致能鎖定 (ENA)、即時中止 (E-Stop) 與軟體極限保護
    """
    def __init__(self, gpio: GPIOBase, config: MotorConfig, is_simulation: bool = False):
        self.gpio = gpio
        self.cfg = config
        self.is_simulation = is_simulation
        
        # 狀態變數
        self.position_steps: int = 0
        self.is_homed: bool = False
        self.is_moving: bool = False
        self.is_locked: bool = True       # 預設馬達通電鎖定 (保持力矩)
        self.abort_requested: bool = False
        self._lock = threading.Lock()
        
        # 硬體引腳初始化
        self.gpio.setup_pin_output(self.cfg.pul_pin, initial_state=0)
        self.gpio.setup_pin_output(self.cfg.dir_pin, initial_state=0)
        self.gpio.setup_pin_output(self.cfg.ena_pin, initial_state=0)
        
        # 初始化致能狀態
        self.set_enable(True)

    @property
    def position_mm(self) -> float:
        return self.position_steps / self.cfg.steps_per_mm

    def set_position_mm(self, mm: float):
        with self._lock:
            self.position_steps = int(round(mm * self.cfg.steps_per_mm))

    def set_enable(self, lock: bool):
        """
        馬達致能鎖定控制:
        lock=True  -> 馬達通電鎖死 (具備保持扭矩，防止負載下墜或位移)
        lock=False -> 馬達離合釋放 (線圈無電流，可用手推動調試)
        
        注意：標準 2HSS86H 步進伺服驅動器之 ENA 引腳：
        預設懸空 (不通光耦) 即為致能運作狀態；光耦通電時為離合釋放。
        若配置了 ena_inverted 則按反相處理。
        """
        with self._lock:
            self.is_locked = lock
            # 預設: 鎖定時 ENA引腳為0 (不導通)，解鎖時ENA引腳為1 (導通以關閉輸出)
            ena_state = 0 if lock else 1
            if self.cfg.ena_inverted:
                ena_state = 1 - ena_state
            self.gpio.write_pin(self.cfg.ena_pin, ena_state)
            logger.info(f"[{self.cfg.name}] 馬達狀態: {'[鎖定致能 - 扭矩保持]' if lock else '[離合解鎖 - 可手動推動]'}")

    def abort(self):
        """緊急停止中斷"""
        self.abort_requested = True
        logger.warning(f"[{self.cfg.name}] 收到運動中止信號！")

    def move_rel(self, delta_mm: float, speed_mm_s: Optional[float] = None, 
                 check_stop_condition: Optional[Callable[[], bool]] = None,
                 ignore_limits: bool = False) -> bool:
        """
        相對位移運動 (含加減速曲線與即時條件檢測)
        """
        target_mm = self.position_mm + delta_mm
        return self.move_abs(target_mm, speed_mm_s, check_stop_condition, ignore_limits=ignore_limits)

    def move_abs(self, target_mm: float, speed_mm_s: Optional[float] = None, 
                 check_stop_condition: Optional[Callable[[], bool]] = None,
                 ignore_limits: bool = False) -> bool:
        """
        絕對座標運動
        """
        if not self.is_locked:
            logger.error(f"[{self.cfg.name}] 馬達目前處於解鎖狀態，禁止執行運動指令！請先致能鎖定。")
            return False

        if self.is_moving:
            logger.warning(f"[{self.cfg.name}] 馬達運動中，忽略新指令")
            return False

        # 軟體行程限制保護 (已歸零狀態下強制校驗，歸零尋點動作可略過)
        if self.is_homed and not ignore_limits:
            if target_mm < self.cfg.min_limit_mm or target_mm > self.cfg.max_limit_mm:
                logger.error(f"[{self.cfg.name}] 目標位置 {target_mm:.2f}mm 超出軟體行程保護範圍 [{self.cfg.min_limit_mm}, {self.cfg.max_limit_mm}]mm！")
                return False

        target_steps = int(round(target_mm * self.cfg.steps_per_mm))
        delta_steps = target_steps - self.position_steps
        if delta_steps == 0:
            return True

        direction = 1 if delta_steps > 0 else -1
        total_steps = abs(delta_steps)
        
        # 決定速度
        max_speed = speed_mm_s if speed_mm_s is not None else self.cfg.max_speed_mm_s
        max_speed = max(1.0, min(max_speed, self.cfg.max_speed_mm_s))
        max_step_rate = max_speed * self.cfg.steps_per_mm
        accel_step_rate = self.cfg.accel_mm_s2 * self.cfg.steps_per_mm
        min_step_rate = 50.0  # 起步頻率 50 steps/s

        # 設定方向引腳
        dir_val = 1 if (direction > 0) else 0
        if self.cfg.dir_inverted:
            dir_val = 1 - dir_val
        self.gpio.write_pin(self.cfg.dir_pin, dir_val)
        time.sleep(0.0005) # 方向引腳建立時間 (2HSS86H 需求 > 5us)

        self.is_moving = True
        self.abort_requested = False
        completed = False

        try:
            # 梯形加減速規劃計算
            # 加速所需步數 = (V_max^2 - V_min^2) / (2 * A)
            accel_steps = int((max_step_rate**2 - min_step_rate**2) / (2.0 * accel_step_rate))
            if 2 * accel_steps > total_steps:
                # 三角形速度曲線 (未達最高速即需減速)
                accel_steps = total_steps // 2
                decel_start_step = total_steps - accel_steps
            else:
                decel_start_step = total_steps - accel_steps

            current_step_rate = min_step_rate
            step_count = 0

            # 模擬模式快速模擬或高頻硬體定時步進
            if self.is_simulation:
                # 模擬環境：平滑批次更新位置，兼顧流暢動畫與快速響應
                batch_size = max(10, int(max_step_rate * 0.03))
                while step_count < total_steps:
                    if self.abort_requested:
                        logger.warning(f"[{self.cfg.name}] 運動被外部請求終止")
                        break
                    if check_stop_condition and check_stop_condition():
                        logger.info(f"[{self.cfg.name}] 觸發停止條件 (感測器觸發)")
                        break

                    steps_to_do = min(batch_size, total_steps - step_count)
                    step_count += steps_to_do
                    with self._lock:
                        self.position_steps += direction * steps_to_do
                    time.sleep(0.005) # 模擬模式快速流暢
                completed = (step_count == total_steps)
            else:
                # 真實樹梅派模式：逐步脈衝產生
                # 2HSS86H 脈衝高低電平脈寬最小需求 > 2.5us
                pul_pin = self.cfg.pul_pin
                write_gpio = self.gpio.write_pin

                while step_count < total_steps:
                    if self.abort_requested:
                        break
                    if check_stop_condition and check_stop_condition():
                        break

                    # 計算目前速率
                    if step_count < accel_steps:
                        # 加速段
                        current_step_rate = math.sqrt(min_step_rate**2 + 2.0 * accel_step_rate * step_count)
                    elif step_count >= decel_start_step:
                        # 減速段
                        remaining = total_steps - step_count
                        current_step_rate = math.sqrt(min_step_rate**2 + 2.0 * accel_step_rate * remaining)
                    else:
                        # 勻速段
                        current_step_rate = max_step_rate

                    interval = 1.0 / max(50.0, current_step_rate)
                    half_interval = interval / 2.0

                    # 輸出一個脈衝
                    write_gpio(pul_pin, 1)
                    time.sleep(max(0.000005, half_interval))
                    write_gpio(pul_pin, 0)
                    time.sleep(max(0.000005, half_interval))

                    step_count += 1
                    with self._lock:
                        self.position_steps += direction

                completed = (step_count == total_steps)

        finally:
            self.is_moving = False
            self.gpio.write_pin(self.cfg.pul_pin, 0)

        return completed

    def get_status(self) -> dict:
        return {
            "name": self.cfg.name,
            "position_mm": round(self.position_mm, 3),
            "position_steps": self.position_steps,
            "is_locked": self.is_locked,
            "is_moving": self.is_moving,
            "is_homed": self.is_homed,
            "steps_per_mm": round(self.cfg.steps_per_mm, 2),
            "max_speed": self.cfg.max_speed_mm_s,
            "min_limit_mm": self.cfg.min_limit_mm,
            "max_limit_mm": self.cfg.max_limit_mm
        }
