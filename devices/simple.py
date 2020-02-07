from device import Device
from collections import deque

from musashi import m68k


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
            ('SR', 0x01, m68k.MEM_SIZE_8, self._read_sr, None),
            ('DR', 0x03, m68k.MEM_SIZE_8, self._read_dr, self._write_dr),
            ('CR', 0x05, m68k.MEM_SIZE_8, self._read_cr, self._write_cr),
            ('VR', 0x06, m68k.MEM_SIZE_8, self._read_vr, self._write_vr),
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
        value = UART.SR_TXRDY
        if len(self._rxfifo) > 0:
            value |= UART.SR_RXRDY
        return value

    def _read_dr(self):
        if len(self._rxfifo) > 0:
            return self._rxfifo.popleft()
        return 0

    def _write_dr(self, value):
        if self._unit == 0:
            self.console_handle_output(chr(value).encode('latin-1'))

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

    def get_interrupt(self):
        if self._interrupting:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if self._interrupting and (interrupt == self._interrupt):
            if self._vr > 0:
                return self._vr
            return m68k.IRQ_AUTOVECTOR
        return m68k.IRQ_SPURIOUS

    @property
    def _interrupting(self):
        if (self._cr & UART.CR_TX_INTEN):
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
            ('PERIOD',  0x00, m68k.MEM_SIZE_32, self._read_period,  self._write_period),
            ('COUNT',   0x04, m68k.MEM_SIZE_32, self._read_count,   None),
            ('CONTROL', 0x09, m68k.MEM_SIZE_8,  self._read_control, self._write_control),
            ('VECTOR',  0x0b, m68k.MEM_SIZE_8,  self._read_vector,  self._write_vector),
        ])
        self._divisor = int(self.cycle_rate / 1000000)  # 1MHz base clock
        self.reset()

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_period(self):
        return self._r_period

    def _read_count(self):
        self.tick()
        return self._r_count

    def _read_control(self):
        return self._r_control

    def _read_vector(self):
        return self._r_vector

    def _write_period(self, value):
        self._r_period = value
        self._r_count = 0
        self._period = (self._r_period + 1) * self._divisor
        self._epoch = self.current_cycle
        self._last_iack = self._epoch
        self._interrupting = False

    def _write_control(self, value):
        self._r_control = value

    def _write_vector(self, value):
        self._r_vector = value

    def tick(self):
        self.tick_deadline = 0
        # do nothing if we are disabled
        count = self.current_cycle - self._epoch
        self._r_count = int((count % self._period) / self._divisor)

        if self._r_control & Timer.CONTROL_INTEN:
            if not self._interrupting:
                iack_loop = int(self._last_iack / self._period)
                this_loop = int(self.current_cycle / self._period)
                if this_loop > iack_loop:
                    self._interrupting = true
                else:
                    self.tick_deadline = (this_loop + 1) * self._period
        else:
            self._interrupting = False

    def reset(self):
        self._r_period = 0
        self._r_count = 0
        self._r_control = 0
        self._r_vector = 0
        self._epoch = 0
        self._period = self._divisor
        self._last_iack = 0

    def get_interrupt(self):
        self.tick()
        if self._interrupting:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if self._interrupting and (interrupt == self._interrupt):
            self._last_iack = self.current_cycle
            self._interrupting = False
            if self._vector > 0:
                return self._vector
            return m68k.IRQ_AUTOVECTOR
        return m68k.IRQ_SPURIOUS
