from device import Device
from collections import deque

from musashi.m68k import (
    M68K_IRQ_SPURIOUS,
    M68K_IRQ_AUTOVECTOR,
    MEM_SIZE_8,
    MEM_SIZE_16,
    MEM_SIZE_32,
)


class UART(Device):
    """
    Simple UART
    """

    SR_RXRDY = 0x01
    SR_TXRDY = 0x02

    CR_RX_INTEN = 0x01
    CR_TX_INTEN = 0x02

    _unit = 0

    def __init__(self, args, address, interrupt):
        super(UART, self).__init__(args=args, name='uart',
                                   address=address, interrupt=interrupt)
        self.add_registers([
            ('SR', 0x01, MEM_SIZE_8, self._read_sr, None),
            ('DR', 0x03, MEM_SIZE_8, self._read_dr, self._write_dr),
            ('CR', 0x05, MEM_SIZE_8, self._read_cr, self._write_cr),
            ('VR', 0x06, MEM_SIZE_8, self._read_vr, self._write_vr),
        ])
        self.reset()
        self._unit = UART._unit
        UART._unit += 1
        if self._unit == 0:
            self.register_console_input_handler(self._handle_console_input)

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_sr(self):
        value = 0
        if self._can_tx:
            value |= UART.SR_TXRDY
        if len(self._rxfifo) > 0:
            value |= UART.SR_RXRDY
        return value

    def _read_dr(self):
        if len(self._rxfifo) > 0:
            return self._rxfifo.popleft()
        return 0

    def _write_dr(self, value):
        if self._can_tx:
            if self._unit == 0:
                self.console_handle_output(chr(value).encode('latin-1'))
            self._last_tx_cycle = self.current_cycle

    def _read_cr(self):
        return self._cr

    def _write_cr(self, value):
        self._cr = value

    def _read_vr(self):
        return self._vr

    def _write_vr(self, value):
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

    CONTROL_INTEN = 0x01

    def __init__(self, args, address, interrupt):
        super(Timer, self).__init__(args=args, name='timer',
                                    address=address, interrupt=interrupt)

        self.add_registers([
            ('PERIOD',  0x00, MEM_SIZE_32, self._read_period,  self._write_period),
            ('COUNT',   0x04, MEM_SIZE_32, self._read_count,   None),
            ('CONTROL', 0x09, MEM_SIZE_8,  self._read_control, self._write_control),
            ('VECTOR',  0x0b, MEM_SIZE_8,  self._read_vector,  self._write_vector),
        ])
        self.reset()

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_period(self):
        return self._period

    def _write_period(self, value):
        self._period = value
        self._count = self._period
        self._epoch = self.current_cycle
        self._last_intr = self._epoch

    def _read_count(self):
        self.tick()
        return self._count

    def _read_control(self):
        return self._control

    def _write_control(self, value):
        self._control = value

    def _read_vector(self):
        return self._vector

    def _write_vector(self, value):
        self._control = value

    def tick(self):
        # do nothing if we are disabled
        if self._period != 0:
            self._count = int((self.current_cycle - self._epoch) / self._divisor) % self._divisor
            if self._control & Timer.CONTROL_INTEN:
                return (self._period - self._count) * self._divisor
        return 0

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
