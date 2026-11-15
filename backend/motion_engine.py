import time
import threading
import logging
from typing import Dict, Any, Optional
from .config import SystemConfig, ConfigManager
from .hardware.gpio_interface import get_gpio
from .hardware.gpio_sim import SimGPIO
from .hardware.motor_axis import MotorAxis
from .hardware.actuators import ElectromagnetController, SensorMonitor

logger = logging.getLogger("MotionEngine")

class MotionEngine:
    """
    雙軸 (X, Z) 運動引擎控制器
    整合步進馬達驅動、接近開關碰撞防護、自動歸零程序與電磁鐵夾取聯動
    """
    def __init__(self, cfg_mgr: ConfigManager):
        self.cfg_mgr = cfg_mgr
        self.cfg: SystemConfig = cfg_mgr.config
        
        # 初始化 GPIO (自動切換真實硬體/模擬模式)
        self.gpio, self.is_simulation = get_gpio(force_simulation=self.cfg.simulation_mode)
        
        # 初始化硬體組件
        self.motor_x = MotorAxis(self.gpio, self.cfg.motor_x, is_simulation=self.is_simulation)
        self.motor_z = MotorAxis(self.gpio, self.cfg.motor_z, is_simulation=self.is_simulation)
        self.electromagnets = ElectromagnetController(self.gpio, self.cfg.electromagnets)
        self.sensor_monitor = SensorMonitor(self.gpio, self.cfg.sensors)
        
        # 系統整體運動狀態: "IDLE", "MOVING", "HOMING", "ESTOP", "ALARM"
        self.state: str = "IDLE"
        self.active_task: Optional[threading.Thread] = None
        self._engine_lock = threading.Lock()
        self._running = True

        # 啟動安全背景監控執行緒 (極限開關觸發保護、模擬感測器同步)
        self._monitor_thread = threading.Thread(target=self._safety_monitor_loop, daemon=True)
        self._monitor_thread.start()

    def reload_config(self, new_cfg: SystemConfig):
        """熱更新運動設定 (速度、細分、加減速、行程限制)"""
        with self._engine_lock:
            self.cfg = new_cfg
            self.motor_x.cfg = new_cfg.motor_x
            self.motor_z.cfg = new_cfg.motor_z
            self.electromagnets.cfg = new_cfg.electromagnets
            self.sensor_monitor.cfg = new_cfg.sensors
            logger.info("運動控制器已成功套用新參數設定")

    def _safety_monitor_loop(self):
        """背景循環：檢測極限開關與驅動器 ALM 報警，實施軟硬體雙重聯鎖保護"""
        while self._running:
            try:
                sensors = self.sensor_monitor.read_all()
                
                # 若為模擬模式，根據虛擬座標自動模擬接近開關狀態
                if self.is_simulation and isinstance(self.gpio, SimGPIO):
                    active_val = 0 if self.cfg.sensors.active_low else 1
                    inactive_val = 1 if self.cfg.sensors.active_low else 0
                    # X軸模擬開關觸發 (Left: <= 2mm, Mid: 290~310mm, Right: >= 598mm)
                    sim_left = active_val if self.motor_x.position_mm <= 2.0 else inactive_val
                    sim_mid = active_val if (295.0 <= self.motor_x.position_mm <= 305.0) else inactive_val
                    sim_right = active_val if self.motor_x.position_mm >= (self.cfg.motor_x.max_limit_mm - 2.0) else inactive_val
                    self.gpio.set_sim_input(self.cfg.sensors.x_left, sim_left)
                    self.gpio.set_sim_input(self.cfg.sensors.x_mid, sim_mid)
                    self.gpio.set_sim_input(self.cfg.sensors.x_right, sim_right)

                    # Z軸模擬開關觸發 (Down: <= 2mm, Up: >= 298mm)
                    sim_down = active_val if self.motor_z.position_mm <= 2.0 else inactive_val
                    sim_up = active_val if self.motor_z.position_mm >= (self.cfg.motor_z.max_limit_mm - 2.0) else inactive_val
                    self.gpio.set_sim_input(self.cfg.sensors.z_down, sim_down)
                    self.gpio.set_sim_input(self.cfg.sensors.z_up, sim_up)

                # 驅動器閉環報警檢測 (X軸 HBS57H、Z軸 HB808C 脫步或過流報警)
                if sensors.get("x_alm") or sensors.get("z_alm"):
                    if self.state not in ["ALARM", "ESTOP"]:
                        logger.error("檢測到閉環驅動器報警輸出 (X軸 HBS57H 或 Z軸 HB808C ALM 觸發)！緊急煞車")
                        self.emergency_stop()
                        self.state = "ALARM"

                time.sleep(0.02) # 50Hz 掃描
            except Exception as e:
                logger.error(f"安全監控執行緒異常: {e}")
                time.sleep(0.1)

    def emergency_stop(self):
        """緊急停止 (E-Stop): 立即中斷所有馬達並處於報警態"""
        logger.warning("[緊急停止] 使用者觸發或系統安全連鎖觸發 E-STOP！")
        self.motor_x.abort()
        self.motor_z.abort()
        self.state = "ESTOP"

    def clear_estop(self):
        """解除緊急停止"""
        self.motor_x.abort_requested = False
        self.motor_z.abort_requested = False
        self.state = "IDLE"
        logger.info("[緊急停止] 已手動重置解除")

    def set_motor_lock(self, axis: str, lock: bool):
        """
        馬達致能鎖定控制 (ENA 控制)
        axis: "X", "Z", 或 "ALL"
        lock: True (通電鎖定，防止下墜/位移), False (離合釋放，手動調試)
        """
        axis = axis.upper()
        if axis in ["X", "ALL"]:
            self.motor_x.set_enable(lock)
        if axis in ["Z", "ALL"]:
            self.motor_z.set_enable(lock)
        logger.info(f"馬達致能狀態切換: 軸向={axis}, 鎖定={lock}")

    def jog(self, axis: str, direction: int, distance_mm: float, speed_mm_s: Optional[float] = None) -> bool:
        """
        寸動 / 點動控制 (Jog)
        axis: "X" or "Z"
        direction: 1 (正向) or -1 (負向)
        distance_mm: 移動距離 (mm)
        """
        if self.state in ["ESTOP", "ALARM"]:
            logger.warning("處於警報或急停狀態，無法執行寸動")
            return False

        if self.motor_x.is_moving or self.motor_z.is_moving:
            logger.warning("馬達運轉中，拒絕新寸動指令")
            return False

        delta = direction * abs(distance_mm)
        axis = axis.upper()
        
        def run_jog():
            self.state = "MOVING"
            try:
                if axis == "X":
                    # X 軸運動並監測對應極限開關 (直接精確讀取對應引腳，避免額外開銷)
                    def stop_check():
                        if self.is_simulation:
                            return False
                        pin = self.cfg.sensors.x_left if direction < 0 else self.cfg.sensors.x_right
                        val = self.gpio.read_pin(pin)
                        return (val == 0) if self.cfg.sensors.active_low else (val == 1)
                    self.motor_x.move_rel(delta, speed_mm_s=speed_mm_s, check_stop_condition=stop_check)
                elif axis == "Z":
                    def stop_check():
                        if self.is_simulation:
                            return False
                        pin = self.cfg.sensors.z_down if direction < 0 else self.cfg.sensors.z_up
                        val = self.gpio.read_pin(pin)
                        return (val == 0) if self.cfg.sensors.active_low else (val == 1)
                    self.motor_z.move_rel(delta, speed_mm_s=speed_mm_s, check_stop_condition=stop_check)
            finally:
                if self.state == "MOVING":
                    self.state = "IDLE"

        threading.Thread(target=run_jog, daemon=True).start()
        return True

    def move_to(self, x: Optional[float] = None, z: Optional[float] = None, speed: Optional[float] = None) -> bool:
        """絕對座標定位移動 (X, Z 聯動或單動)"""
        if self.state in ["ESTOP", "ALARM"]:
            return False
        if self.motor_x.is_moving or self.motor_z.is_moving:
            return False

        def run_move():
            self.state = "MOVING"
            try:
                # 為了避免工件碰撞，若 Z 軸需要向上提升，先提升 Z，再移動 X
                # 若 Z 軸需要向下，先移動 X 到位，再下降 Z
                if z is not None and z > self.motor_z.position_mm:
                    self.motor_z.move_abs(z, speed_mm_s=speed)
                if x is not None:
                    self.motor_x.move_abs(x, speed_mm_s=speed)
                if z is not None and z <= self.motor_z.position_mm:
                    self.motor_z.move_abs(z, speed_mm_s=speed)
            finally:
                if self.state == "MOVING":
                    self.state = "IDLE"

        threading.Thread(target=run_move, daemon=True).start()
        return True

    def start_homing(self, axes: str = "ALL"):
        """
        全自動原點復歸 (Auto Homing Routine)
        安全順序：
        1. 先歸零 Z 軸 (垂直軸上升至最高安全位置，避免手臂末端在低空橫移撞擊機構)
        2. 再歸零 X 軸 (水平橫移至左端原點)
        """
        if self.state in ["ESTOP", "ALARM", "HOMING"]:
            logger.warning(f"目前狀態為 {self.state}，無法啟動自動歸零")
            return False

        def homing_routine():
            self.state = "HOMING"
            logger.info("=== 啟動自動原點復歸序列 (Auto Homing) ===")
            try:
                # 確保兩軸馬達致能鎖定
                self.motor_x.set_enable(True)
                self.motor_z.set_enable(True)
                time.sleep(0.1)

                target_axes = axes.upper()

                # --- 步驟 1: Z 軸歸零 (向上移動，直到碰到頂部電感式接近開關 Z_UP) ---
                if target_axes in ["ALL", "Z"]:
                    self.motor_z.is_homed = False
                    logger.info(">>> 執行 Z 軸安全歸零 (向上移動，直到碰到頂部電感式接近開關 Z_UP)...")
                    z_cfg = self.cfg.motor_z

                    # 即時精準檢測頂部電感接近開關 (Z_UP)
                    def is_z_up_hit() -> bool:
                        if self.is_simulation:
                            return self.motor_z.position_mm >= (z_cfg.max_limit_mm - 2.0)
                        val = self.gpio.read_pin(self.cfg.sensors.z_up)
                        return (val == 0) if self.cfg.sensors.active_low else (val == 1)

                    # 若初始已在頂部開關觸發狀態，先緩慢向下微退，直到脫離開關
                    if is_z_up_hit():
                        logger.info("Z 軸初始已在頂部開關上，先緩慢向下微退...")
                        self.motor_z.move_rel(-1 * z_cfg.backoff_mm, speed_mm_s=z_cfg.creep_speed_mm_s, ignore_limits=True)
                        time.sleep(0.05)

                    # 向上移動尋找開關，直到碰到開關停止
                    max_travel = z_cfg.max_limit_mm - z_cfg.min_limit_mm + 50.0
                    self.motor_z.move_rel(1 * max_travel, speed_mm_s=z_cfg.homing_speed_mm_s, check_stop_condition=is_z_up_hit, ignore_limits=True)
                    if self.state == "ESTOP": return

                    # 設定原點座標
                    self.motor_z.set_position_mm(z_cfg.home_offset_mm)
                    self.motor_z.is_homed = True
                    logger.info(f"Z 軸已觸碰頂部接近開關 (Z_UP) 停止！歸零完成，已校準座標為 {z_cfg.home_offset_mm:.2f}mm")

                # --- 步驟 2: X 軸歸零 (向左移動，直到碰到左端電感式接近開關 X_LEFT) ---
                if target_axes in ["ALL", "X"]:
                    self.motor_x.is_homed = False
                    logger.info(">>> 執行 X 軸歸零 (向左移動，直到碰到左端電感式接近開關 X_LEFT)...")
                    x_cfg = self.cfg.motor_x

                    # 即時精準檢測左端電感接近開關 (X_LEFT)
                    def is_x_left_hit() -> bool:
                        if self.is_simulation:
                            return self.motor_x.position_mm <= 2.0
                        val = self.gpio.read_pin(self.cfg.sensors.x_left)
                        return (val == 0) if self.cfg.sensors.active_low else (val == 1)

                    # 若初始已在左端開關觸發狀態，先緩慢向右微退，直到脫離開關
                    if is_x_left_hit():
                        logger.info("X 軸初始已在左端開關上，先緩慢向右微退...")
                        self.motor_x.move_rel(1 * x_cfg.backoff_mm, speed_mm_s=x_cfg.creep_speed_mm_s, ignore_limits=True)
                        time.sleep(0.05)

                    # 向左移動尋找開關，直到碰到開關停止
                    max_travel = x_cfg.max_limit_mm - x_cfg.min_limit_mm + 50.0
                    self.motor_x.move_rel(-1 * max_travel, speed_mm_s=x_cfg.homing_speed_mm_s, check_stop_condition=is_x_left_hit, ignore_limits=True)
                    if self.state == "ESTOP": return

                    # 設定原點座標
                    self.motor_x.set_position_mm(x_cfg.home_offset_mm)
                    self.motor_x.is_homed = True
                    logger.info(f"X 軸已觸碰左邊接近開關 (X_LEFT) 停止！歸零完成，已校準座標為 {x_cfg.home_offset_mm:.2f}mm")

                logger.info("=== 全自動歸零作業圓滿完成！===")
            except Exception as e:
                logger.error(f"歸零程序中斷或發生異常: {e}")
            finally:
                if self.state == "HOMING":
                    self.state = "IDLE"

        self.active_task = threading.Thread(target=homing_routine, daemon=True)
        self.active_task.start()
        return True

    def get_telemetry(self) -> Dict[str, Any]:
        """產生完整即時遙測封包 (供 WebSocket 高頻推播)"""
        return {
            "timestamp": time.time(),
            "state": self.state,
            "is_simulation": self.is_simulation,
            "motor_x": self.motor_x.get_status(),
            "motor_z": self.motor_z.get_status(),
            "sensors": self.sensor_monitor.read_all(),
            "electromagnets": self.electromagnets.get_states()
        }
