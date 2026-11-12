from abc import ABC, abstractmethod

class GPIOBase(ABC):
    @abstractmethod
    def setup_pin_input(self, pin: int, pull_up: bool = True):
        pass

    @abstractmethod
    def setup_pin_output(self, pin: int, initial_state: int = 0):
        pass

    @abstractmethod
    def read_pin(self, pin: int) -> int:
        pass

    @abstractmethod
    def write_pin(self, pin: int, value: int):
        pass

    @abstractmethod
    def cleanup(self):
        pass
