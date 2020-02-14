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

    def __init__(self, args, **options):
        super(UART, self).__init__(args=args,
                                   name='uart',
                                   required_options=['address', 'interrupt'],
                                   **options)
        self.add_registers([
            ('SR', 0x01, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_sr),
            ('DR', 0x03, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_dr),
            ('CR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cr),
            ('VR', 0x06, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_vr),

            ('DR', 0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_dr),
            ('CR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_cr),
            ('VR', 0x06, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_vr),
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
            self._update_ipl()
        return 0

    def _write_dr(self, value):
        if self._unit == 0:
            self.console_handle_output(chr(value).encode('latin-1'))

    def _read_cr(self):
        return self._cr

    def _write_cr(self, value):
        self._cr = value
        self._update_ipl()

    def _read_vr(self):
        return self._vr

    def _write_vr(self, value):
        self._vr = value

    def reset(self):
        self._rxfifo = deque()
        self._vr = 0
        self._cr = 0

    def _update_ipl(self):
        if (self._cr & UART.CR_TX_INTEN):
            self.assert_ipl()
        elif (self._cr & UART.CR_RX_INTEN) and len(self._rxfifo) > 0:
            self.assert_ipl()
        else:
            self.deassert_ipl()

    def get_vector(self, interrupt):
        if self._vr > 0:
            return self._vr
        return m68k.IRQ_AUTOVECTOR

    def _handle_console_input(self, input):
        for c in input:
            self._rxfifo.append(c)
        self._update_ipl()


class Timer(Device):
    """
    A simple timebase; reports absolute time in microseconds, and counts down
    microseconds and generates an interrupt.
    """

    def __init__(self, args, **options):
        super(Timer, self).__init__(args=args,
                                    name='timer',
                                    required_options=['address', 'interrupt'],
                                    **options)

        self.add_registers([
            ('COUNT',   0x00, m68k.MEM_SIZE_32, m68k.MEM_READ,  self._read_timebase),
            ('VECTOR',  0x05, m68k.MEM_SIZE_8,  m68k.MEM_READ,  self._read_vector),

            ('COUNT',   0x00, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_countdown),
            ('VECTOR',  0x05, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_vector),
        ])
        self._scaler = int(self.cycle_rate / 1000000)  # 1MHz base clock
        self.reset()

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_timebase(self):
        return int(self.current_cycle / self._scaler)

    def _read_vector(self):
        return self._r_vector

    def _write_countdown(self, value):
        if value == 0:
            self.deassert_ipl()
            self._deadline = 0
            self.callback_cancel('count')
            self.trace('timer cancelled')
        else:
            self._deadline = self.current_cycle + value * self._scaler
            self.callback_at(self._deadline, 'count', self._callback)
            self.trace(f'timer set for {self._deadline}, now {self.current_cycle}')

    def _write_vector(self, value):
        self._r_vector = value

    def _callback(self):
        if (self._deadline > 0):
            if (self._deadline <= self.current_cycle):
                self.trace('timer expired')
                self.assert_ipl()
                self._deadline = 0
            else:
                self.trace('spurious callback')
                self.callback_at(self._deadline, 'count', self._callback)

    def reset(self):
        self._deadline = 0
        self._r_vector = 0
        self.deassert_ipl()
        self.callback_cancel('count')

    def get_vector(self, interrupt):
        self.deassert_ipl()
        if self._r_vector > 0:
            return self._r_vector
        return m68k.IRQ_AUTOVECTOR
