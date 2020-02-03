from device import Device
from collections import deque

from musashi.m68k import (
    M68K_IRQ_SPURIOUS,
    M68K_IRQ_AUTOVECTOR,
)


class UART(Device):
    """
    Simple UART
    """

    _registers = {
        'SR': 0x01,
        'DR': 0x03,
        'CR': 0x05,
        'VR': 0x07,
    }
    SR_RXRDY = 0x01
    SR_TXRDY = 0x02

    CR_RX_INTEN = 0x01
    CR_TX_INTEN = 0x02

    _unit = 0

    def __init__(self, args, address, interrupt):
        super(UART, self).__init__(args=args, name='uart',
                                   address=address, interrupt=interrupt)
        self.map_registers(self._registers)
        self.reset()
        self._unit = UART._unit
        UART._unit += 1
        if self._unit == 0:
            self.register_console_input_handler(self._handle_console_input)

    @classmethod
    def add_arguments(self, parser):
        pass

    def read(self, width, addr):
        value = 0
        if width == Device.WIDTH_8:
            if addr == self._registers['SR']:
                if self._can_tx:
                    value |= UART.SR_TXRDY
                if len(self._rxfifo) > 0:
                    value |= UART.SR_RXRDY
            elif addr == self._registers['DR']:
                if len(self._rxfifo) > 0:
                    value = self._rxfifo.popleft()
            elif addr == self._registers['CR']:
                value = self._cr
            elif addr == self._registers['VR']:
                value = self._vr

        return value

    def write(self, width, addr, value):
        if width == Device.WIDTH_8:
            if addr == self._registers['DR']:
                if self._can_tx:
                    if self._unit == 0:
                        self.console_handle_output(chr(value).encode('latin-1'))
                    self._last_tx_cycle = self.current_cycle
            elif addr == self._registers['CR']:
                self._cr = value
            elif addr == self._registers['VR']:
                self._vr = value

    def reset(self):
        self._rxfifo = deque()
        self._vr = 0
        self._cr = 0
        self._last_tx_cycle = 0

    def get_interrupt(self):
        if self._interrupting:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if self._interrupting and (interrupt == self._interrupt):
            if self._vr > 0:
                return self._vr
            return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS

    @property
    def _can_tx(self):
        # pace transmit to one character every 1000 cycles
        return self.current_cycle > (self._last_tx_cycle + 1000)

    @property
    def _interrupting(self):
        if (self._cr & UART.CR_TX_INTEN) and self._can_tx:
            return True
        if (self._cr & UART.CR_RX_INTEN) and len(self._rxfifo) > 0:
            return True
        return False

    def _handle_console_input(self, input):
        for c in input:
            self._rxfifo.append(c)


class Timer(Device):
    """
    A simple up-counting timer with programmable period
    """

    _registers = {
        'PERIOD': 0x00,
        'COUNT': 0x04,
        'CONTROL': 0x09,
        'VECTOR': 0x0b,
    }
    CONTROL_INTEN = 0x01

    def __init__(self, args, address, interrupt):
        super(Timer, self).__init__(args=args, name='timer',
                                    address=address, interrupt=interrupt)
        self.map_registers(self._registers)
        self.reset()

    @classmethod
    def add_arguments(self, parser):
        pass

    def read(self, width, addr):
        value = 0
        if width == Device.WIDTH_32:
            if addr == self._registers['PERIOD']:
                value = self._period
            if addr == self._registers['COUNT']:
                self.tick()
                value = self._count
        elif width == Device.WIDTH_8:
            if addr == self._registers['CONTROL']:
                value = self._control
            if addr == self._registers['VECTOR']:
                value = self._vector
        return value

    def write(self, width, addr, value):
        if width == Device.WIDTH_32:
            if addr == self._registers['PERIOD']:
                self._period = value
                self._count = self._period
                self._epoch = self.current_cycle
                self._last_intr = self._epoch
        elif width == Device.WIDTH_8:
            if addr == self._registers['CONTROL']:
                self._control = value
            if addr == self._registers['VECTOR']:
                self._vector = value

    def tick(self):
        # do nothing if we are disabled
        if self._period != 0:
            self._count = int((self.current_cycle - self._epoch) / self._divisor) % self._divisor
            if self._control & Timer.CONTROL_INTEN:
                return (self._period - self._count) * self._divisor

    def reset(self):
        self._divisor = int(self.cycle_rate / 1000000)  # 1MHz base clock
        self._period = 0
        self._count = 0
        self._control = 0
        self._vector = 0
        self._epoch = 0
        self._last_intr = 0

    def get_interrupt(self):
        if self._interrupting:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if self._interrupting and (interrupt == self._interrupt):
            if self._vector > 0:
                return self._vector
            return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS

    @property
    def _interrupting(self):
        if not (self._control & Timer.CONTROL_INTEN):
            return False
        if not (self._last_intr + (self._period * self._divisor)) > self.current_cycle:
            return False
        return True
