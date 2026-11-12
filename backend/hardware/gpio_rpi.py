import logging
from .gpio_base import GPIOBase

logger = logging.getLogger("HardwareGPIO")

class RPiGPIO(GPIOBase):
    def __init__(self):
        self.driver = None
        self._init_driver()

    def _init_driver(self):
        try:
            import RPi.GPIO as GPIO
            self.GPIO = GPIO
            self.GPIO.setmode(GPIO.BCM)
            self.GPIO.setwarnings(False)
            self.driver = "RPi.GPIO"
            logger.info("成功載入 RPi.GPIO 模組 (BCM模式)")
            return
        except (ImportError, RuntimeError):
            pass

        try:
            import lgpio
            self.lgpio = lgpio
            self.chip = lgpio.gpiochip_open(0)
            self.driver = "lgpio"
            logger.info("成功載入 lgpio 模組 (Raspberry Pi 5 / Bookworm)")
            return
        except (ImportError, RuntimeError):
            pass

        raise ImportError("未檢測到可用的樹梅派 GPIO 硬體庫 (RPi.GPIO 或 lgpio)")

    def setup_pin_input(self, pin: int, pull_up: bool = True):
        if self.driver == "RPi.GPIO":
            pud = self.GPIO.PUD_UP if pull_up else self.GPIO.PUD_DOWN
            self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=pud)
        elif self.driver == "lgpio":
            flags = self.lgpio.SET_PULL_UP if pull_up else self.lgpio.SET_PULL_DOWN
            self.lgpio.gpio_claim_input(self.chip, pin, flags)

    def setup_pin_output(self, pin: int, initial_state: int = 0):
        if self.driver == "RPi.GPIO":
            self.GPIO.setup(pin, self.GPIO.OUT, initial=initial_state)
        elif self.driver == "lgpio":
            self.lgpio.gpio_claim_output(self.chip, pin, initial_state)

    def read_pin(self, pin: int) -> int:
        if self.driver == "RPi.GPIO":
            return self.GPIO.input(pin)
        elif self.driver == "lgpio":
            return self.lgpio.gpio_read(self.chip, pin)
        return 0

    def write_pin(self, pin: int, value: int):
        val = 1 if value else 0
        if self.driver == "RPi.GPIO":
            self.GPIO.output(pin, val)
        elif self.driver == "lgpio":
            self.lgpio.gpio_write(self.chip, pin, val)

    def cleanup(self):
        if self.driver == "RPi.GPIO":
            self.GPIO.cleanup()
        elif self.driver == "lgpio":
            self.lgpio.gpiochip_close(self.chip)
        logger.info("GPIO 硬體資源已釋放清理")

