import os
import json
from pydantic import BaseModel, Field
from typing import Dict, Any

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")

class MotorConfig(BaseModel):
    name: str
    pul_pin: int
    dir_pin: int
    ena_pin: int
    alm_pin: int = -1
    steps_per_rev: int = 1600         # 驅動器微步細分 (例如 1600 pulse/rev)
    pitch_mm_per_rev: float = 5.0     # 導程或每轉移動毫米 (如 5mm 滾珠螺桿 或 40mm 同步輪)
    max_speed_mm_s: float = 80.0      # 最高移動速度 (mm/s)
    homing_speed_mm_s: float = 20.0   # 快速歸零尋點速度 (mm/s)
    creep_speed_mm_s: float = 4.0     # 二次精確觸碰速度 (mm/s)
    accel_mm_s2: float = 300.0        # 加速度 (mm/s²)
    min_limit_mm: float = 0.0         # 軟體行程下限 min_limit_mm (mm)
    max_limit_mm: float = 600.0       # 軟體行程上限 max_limit_mm (mm)
    dir_inverted: bool = False        # 方向反轉
    ena_inverted: bool = False        # 致能信號反轉 (HBS57H / HB808C 預設 ENA 未導通為馬達鎖定，導通為釋放)
    home_direction: int = -1          # 歸零方向: -1 (往最小極限), 1 (往最大極限)
    home_offset_mm: float = 0.0       # 歸零後設定座標 (mm)
    backoff_mm: float = 5.0           # 第一次觸碰後的退回距離 (mm)

    @property
    def steps_per_mm(self) -> float:
        if self.pitch_mm_per_rev <= 0:
            return 320.0
        return self.steps_per_rev / self.pitch_mm_per_rev

class SensorPinConfig(BaseModel):
    # X軸 3個接近開關 (QN-1805-E1)
    x_left: int = 17    # Pin 11 (X-Left / X極限與歸零原點)
    x_mid: int = 27     # Pin 13 (X-Mid / X中間工位檢測)
    x_right: int = 22   # Pin 15 (X-Right / X右極限)
    
    # Z軸 2個接近開關
    z_up: int = 10      # Pin 19 (Z-Up / Z上極限與安全歸零點)
    z_down: int = 9     # Pin 21 (Z-Down / Z下極限)
    
    # 手臂末端 8個接近開關
    arm_1: int = 11     # Pin 23 (手臂末端測針/夾爪 1)
    arm_2: int = 5      # Pin 29 (手臂末端測針/夾爪 2)
    arm_3: int = 6      # Pin 31 (手臂末端測針/夾爪 3)
    arm_4: int = 13     # Pin 33 (手臂末端測針/夾爪 4)
    arm_5: int = 19     # Pin 35 (手臂末端測針/夾爪 5)
    arm_6: int = 26     # Pin 37 (手臂末端測針/夾爪 6)
    arm_7: int = 16     # Pin 36 (手臂末端測針/夾爪 7)
    arm_8: int = 20     # Pin 38 (手臂末端測針/夾爪 8)

    # 警報引腳 (驅動器 ALM)
    x_alm: int = 21     # Pin 40 (HBS57H-X 警報)
    z_alm: int = 25     # Pin 22 (HB808C-Z 警報)

    # 接近開關邏輯電平 (光耦隔離後: NPN NO 檢測到金屬時導通接地為 LOW，若為 False 則為 HIGH 有效)
    active_low: bool = False

class ElectromagnetConfig(BaseModel):
    # 4組 LSD-P25/20 電磁鐵輸出引腳
    em1_pin: int = 4    # Pin 7 (電磁鐵 1)
    em2_pin: int = 14   # Pin 8 (電磁鐵 2)
    em3_pin: int = 15   # Pin 10 (電磁鐵 3)
    em4_pin: int = 2    # Pin 3 (電磁鐵 4)
    active_high: bool = True           # GPIO HIGH 時通電吸附
    auto_off_timeout_sec: int = 0      # 0代表不自動斷電；>0 代表通電超時自動斷電 (保護線圈)

class SystemConfig(BaseModel):
    app_name: str = "雙軸龍門機械手臂智能控制系統"
    version: str = "2.1.0"
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    simulation_mode: bool = False      # 自動偵測，或手動強制模擬
    
    # 馬達設定
    motor_x: MotorConfig = Field(default_factory=lambda: MotorConfig(
        name="X軸馬達 (HBS57H + 57BYG-112)",
        pul_pin=18,    # Pin 12 (硬體PWM相容)
        dir_pin=23,    # Pin 16
        ena_pin=24,    # Pin 18
        alm_pin=21,    # Pin 40
        steps_per_rev=1600,
        pitch_mm_per_rev=40.0,   # 例如皮帶傳動 40mm/rev 或 滾珠螺桿
        max_speed_mm_s=120.0,
        homing_speed_mm_s=25.0,
        creep_speed_mm_s=5.0,
        accel_mm_s2=400.0,
        min_limit_mm=0.0,
        max_limit_mm=600.0,
        home_direction=-1,
        home_offset_mm=0.0,
        backoff_mm=8.0
    ))
    
    motor_z: MotorConfig = Field(default_factory=lambda: MotorConfig(
        name="Z軸雙馬達同步 (HB808C + 雙 57BYG-112)",
        pul_pin=12,    # Pin 32 (硬體PWM相容)
        dir_pin=8,     # Pin 24
        ena_pin=7,     # Pin 26
        alm_pin=25,    # Pin 22
        steps_per_rev=1600,
        pitch_mm_per_rev=5.0,    # 滾珠螺桿 5mm/rev
        max_speed_mm_s=40.0,
        homing_speed_mm_s=15.0,
        creep_speed_mm_s=3.0,
        accel_mm_s2=250.0,
        min_limit_mm=0.0,
        max_limit_mm=300.0,
        home_direction=1,        # 向上歸零 (安全高度)
        home_offset_mm=300.0,    # 頂端為 300.0mm (或0.0mm視習慣)
        backoff_mm=5.0
    ))
    
    sensors: SensorPinConfig = Field(default_factory=SensorPinConfig)
    electromagnets: ElectromagnetConfig = Field(default_factory=ElectromagnetConfig)

class ConfigManager:
    def __init__(self, filepath: str = CONFIG_FILE_PATH):
        self.filepath = filepath
        self.config: SystemConfig = self.load()

    def load(self) -> SystemConfig:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return SystemConfig(**data)
            except Exception as e:
                print(f"[ConfigManager] 讀取設定檔失敗，將建立預設設定: {e}")
        cfg = SystemConfig()
        self.save(cfg)
        return cfg

    def save(self, cfg: SystemConfig = None) -> bool:
        if cfg is not None:
            self.config = cfg
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.config.model_dump(), f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] 儲存設定檔失敗: {e}")
            return False

# 全域單例
config_mgr = ConfigManager()

