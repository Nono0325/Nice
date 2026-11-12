import logging
from .gpio_base import GPIOBase
from .gpio_sim import SimGPIO
from .gpio_rpi import RPiGPIO

logger = logging.getLogger("GPIOFactory")

_gpio_instance: GPIOBase = None
_is_simulation: bool = False

def get_gpio(force_simulation: bool = False) -> tuple[GPIOBase, bool]:
    global _gpio_instance, _is_simulation
    if _gpio_instance is not None:
        return _gpio_instance, _is_simulation

    if not force_simulation:
        try:
            _gpio_instance = RPiGPIO()
            _is_simulation = False
            logger.info("檢測到硬體環境，已啟用真實樹梅派 GPIO 硬體驅動")
            return _gpio_instance, _is_simulation
        except Exception as e:
            logger.warning(f"未能載入樹梅派硬體 GPIO ({e})，自動切換至虛擬模擬模式 (Simulation Mode)")

    _gpio_instance = SimGPIO()
    _is_simulation = True
    return _gpio_instance, _is_simulation
