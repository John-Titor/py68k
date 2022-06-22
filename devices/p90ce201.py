from collections import deque
import sys

from device import Device
from musashi import m68k

ADDR_P90Syscon = 0x80001000
ADDR_P90ICU = 0x80001020
ADDR_P90I2C1 = 0x80002000
ADDR_P90I2C2 = 0x80002010
ADDR_P90UART = 0x80002020
ADDR_P90Timer0 = 0x80002030
ADDR_P90Timer1 = 0x80002040
ADDR_P90Timer2 = 0x80002050
ADDR_P90Watchdog = 0x80002060
ADDR_P90GPIO = 0x80002070
ADDR_P90AUX = 0x80002080


def add_arguments(parser, default_crystal_frequency=24):
    parser.add_argument('--p90-crystal-frequency',
                        type=int,
                        choices=range(1, 24),
                        default=default_crystal_frequency,
                        metavar='FREQUENCY-MHZ',
                        help='P90CE201 clock crystal frequency')


def add_devices(args, emu, crystal_frequency):
    emu.add_device(args,
                   P90Syscon,
                   address=ADDR_P90Syscon,
                   fclk=crystal_frequency)
    emu.add_device(args,
                   P90UART,
                   address=ADDR_P90UART)
    emu.add_device(args,
                   P90Timer,
                   address=ADDR_P90Timer0)
    emu.add_device(args,
                   P90Timer,
                   address=ADDR_P90Timer1)
    emu.add_device(args,
                   P90Timer,
                   address=ADDR_P90Timer2)
    emu.add_device(args,
                   P90Watchdog,
                   address=ADDR_P90Watchdog)
#    emu.add_device(args,
#                   P90GPIO,
#                   address=ADDR_P90GPIO)
    emu.add_device(args,
                   P90AUX,
                   address=ADDR_P90AUX)


class P90Syscon(Device):

    def __init__(self, args, address, fclk):
        super(P90Syscon, self).__init__(args=args,
                                        name='P90Syscon',
                                        address=address)

        self.add_registers([
            ('SYSCON1', 0x00, m68k.MEM_SIZE_16, m68k.MEM_READ,  self._read_syscon1),
            ('SYSCON2', 0x02, m68k.MEM_SIZE_16, m68k.MEM_READ,  self._read_syscon2),

            ('SYSCON1', 0x00, m68k.MEM_SIZE_16, m68k.MEM_WRITE, self._write_syscon1),
            ('SYSCON2', 0x02, m68k.MEM_SIZE_16, m68k.MEM_WRITE, self._write_syscon2),
        ])

        self._fclk = fclk
        self.reset()

    def _read_syscon1(self):
        return self._syscon1

    def _read_syscon2(self):
        return self._syscon2

    def _write_syscon1(self, value):
        self._syscon1 = value

    def _write_syscon2(self, value):
        self._syscon2 = value

    def reset(self):
        self._syscon1 = 0x0000
        self._syscon2 = 0x0008

    def timer_prescaler(self, timer_id):
        prescaler = 1
        if (timer_id == 0):
            prescaler = 32 if (self._syscon2 & 0x0010) else 2
        if (timer_id == 1):
            prescaler = 32 if (self._syscon2 & 0x0002) else 2
        if (timer_id == 2):
            prescaler = int(self._bpclk_divisor * 4) if (self._syscon2 & 0x0400) else 2
        return prescaler

    def timer_clk(self, timer_id):
        return int(self._fclk / self.timer_prescaler(timer_id))

    @property
    def cpu_prescaler(self):
        return 2

    @property
    def cpu_clk(self):
        return self._fclk / self.cpu_prescaler

    @property
    def bpclk_divisor(cls):
        sel = (self._syscon2 >> 8) & 3
        if sel == 0:
            return 3
        elif sel == 1:
            return 2.5
        elif sel == 2:
            return 2
        elif sel == 3:
            return 1.5


class P90UART(Device):

    def __init__(self, args, address):
        super(P90UART, self).__init__(args=args,
                                      name='P90UART',
                                      address=address)

        self.add_registers([
            ('SBUF', 0x01, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_sbuf),
            ('SCON', 0x03, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_scon),
            ('URIR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_urir),
            ('URIV', 0x07, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_uriv),
            ('UTIR', 0x09, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_utir),
            ('UTIV', 0x0b, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_utiv),

            ('SBUF', 0x01, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_sbuf),
            ('SCON', 0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_scon),
            ('URIR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_urir),
            ('URIV', 0x07, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_uriv),
            ('UTIR', 0x09, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_utir),
            ('UTIV', 0x0b, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_utiv),
        ])
        self._rxfifo = deque()
        self.register_console_input_handler(self._handle_console_input)
        self.reset()

    def _read_sbuf(self):
        if len(self._rxfifo) > 0:
            value = self._rxfifo.popleft()
            # self.callback_after(P90Timer.uart_rx_period() * 10, 'rxrdy', self._rx_done)
            self.callback_after(100, 'rxrdy', self._rx_done)
        else:
            value = 0xff
        return value

    def _read_scon(self):
        return self._scon

    def _read_urir(self):
        return self._urir

    def _read_uriv(self):
        return self._uriv

    def _read_utir(self):
        return self._utir

    def _read_utiv(self):
        return self._utiv

    def _write_sbuf(self, value):
        self.console_handle_output(chr(value).encode('latin-1'))
        # self.callback_after(P90Timer.uart_tx_period() * 10, 'txrdy', self._tx_done)
        self.callback_after(100, 'txrdy', self._tx_done)

    def _write_scon(self, value):
        self._scon = value

    def _write_urir(self, value):
        self._urir = value
        self._update_ipl()

    def _write_uriv(self, value):
        self._uriv = value

    def _write_utir(self, value):
        self._utir = value
        self._update_ipl()

    def _write_utiv(self, value):
        self._utiv = value

    def reset(self):
        self._scon = 0
        self._urir = 0
        self._uriv = 0x0f
        self._utir = 0
        self._utiv = 0x0f

    def get_interrupt(self):
        if ((self._urir & 0x0f) > 0x08):
            return self._urir & 7
        if ((self._utir & 0xf) > 0x08):
            return self._utir & 7

    def get_vector(self, interrupt):
        if interrupt == self._urir & 7:
            if (self._urir & 0x08):
                self._urir &= ~0x08
                if (self._urir & 0x20):
                    return self._uriv
                else:
                    return M68K_IRQ_AUTOVECTOR
        if interrupt == self._utir & 7:
            if (self._utir & 0x08):
                self._utir &= ~0x08
                if (self._utir & 0x20):
                    return self._utiv
                else:
                    return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS

    def _tx_done(self):
        self._scon |= 0x02  # transmit complete status
        self._update_ipl()

    def _rx_done(self):
        self._update_status()

    def _update_status(self):
        if len(self._rxfifo) > 0:
            self._scon |= 0x01
            self._urir |= 0x08
        self._update_ipl()

    def _update_ipl(self):
        ipl = 0
        if (self._scon & 0x01) and ((self._urir & 7) > ipl):
            ipl = self._urir & 7
        if (self._scon & 0x02) and ((self._utir & 7) > ipl):
            ipl = self._utir & 7
        self.assert_ipl(ipl)

    def _handle_console_input(self, input):
        if self._scon & 0x10:
            was_idle = len(self._rxfifo) == 0
            for c in input:
                self._rxfifo.append(c)
            if was_idle:
                self._update_status()


class P90Timer(Device):
    timers = []

    def __init__(self, args, address):
        self._syscon = Device.find_device('P90Syscon')
        if address == ADDR_P90Timer0:
            self._timer_id = 0
        elif address == ADDR_P90Timer1:
            self._timer_id = 1
        elif address == ADDR_P90Timer2:
            self._timer_id = 2
        super(P90Timer, self).__init__(args=args,
                                       name=f'P90Timer{self._timer_id}',
                                       address=address)

        P90Timer.timers.append(self)

        self.add_registers([
            ('T',    0x00, m68k.MEM_SIZE_16, m68k.MEM_READ, self._read_t),
            ('RCAP', 0x02, m68k.MEM_SIZE_16, m68k.MEM_READ, self._read_rcap),
            ('TCON', 0x05, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_tcon),
            ('TIR',  0x07, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_tir),
            ('TIV',  0x09, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_tiv),

            ('T',    0x00, m68k.MEM_SIZE_16, m68k.MEM_WRITE, self._write_t),
            ('RCAP', 0x02, m68k.MEM_SIZE_16, m68k.MEM_WRITE, self._write_rcap),
            ('TCON', 0x05, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_tcon),
            ('TIR',  0x07, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_tir),
            ('TIV',  0x09, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_tiv),
        ])
        self.reset()

    def _read_t(self):
        # if counting, need an updated value for T
        if self._is_counting:
            self._update_t()
        return self._t

    def _read_rcap(self):
        return self._rcap

    def _read_tcon(self):
        return self._tcon

    def _read_tir(self):
        return self._tir

    def _read_tiv(self):
        return self._tiv

    def _write_t(self, value):
        self._t = value
        if self._is_counting:
            self._start_counting()

    def _write_rcap(self, value):
        self._rcap = value

    def _write_tcon(self, value):
        was_counting = self._is_counting
        self._tcon = value
        self._update_ipl()
        if self._is_counting and not was_counting:
            # counting started - register for overflow callback
            self._start_counting()
        else:
            # counting stopped - update T
            self._update_t()
            # ... and deregister overflow callback
            self._stop_counting()

    def _write_tir(self, value):
        self._tir = value
        self._update_ipl()

    def _write_tiv(self, value):
        self._tiv = value

    def reset(self):
        self._t = 0
        self._t_epoch = 0
        self._rcap = 0
        self._tcon = 0
        self._tir = 0
        self._tiv = 0
        self._stop_counting()

    def _update_ipl(self):
        if self._tcon & 0x80:
            self._tir |= 0x08
            self.assert_ipl(self._tir & 0x7)
        else:
            self.assert_ipl(0)

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            if (self._tir & 0x08):
                self._tir &= ~0x08
                if (self._tir & 0x20):
                    return self._tiv
                else:
                    return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS

    @classmethod
    def uart_tx_period(cls):
        for t in cls.timers:
            if t._tcon & 0x10:
                return t._period_cycles
        # return something slow but sane
        return 1000

    @classmethod
    def uart_rx_period(cls):
        for t in cls.timers:
            if t._tcon & 0x20:
                return t._period_cycles
        # return something slow but sane
        return 1000

    @property
    def _prescaler(self):
        return self._syscon.timer_prescaler(self._timer_id)

    @property
    def _period_cycles(self):
        # period in base clocks
        clks = (0x10000 - self._rcap) * self._prescaler
        # convert to CPU cycles
        return int(clks / self._syscon.cpu_prescaler)

    @property
    def _remaining_cycles(self):
        # remaining time in base clocks
        clks = (0x10000 - self._t) * self._prescaler
        # return time in CPU cycles
        return int(clks / self._syscon.cpu_prescaler)

    @property
    def _is_counting(self):
        return (self._tcon & 0x06) == 0x04

    def _update_t(self):
        # CPU cycles since T was set
        elapsed_cycles = self.current_cycle - self._t_epoch
        # base clock cycles since T was set
        elapsed_clks = elapsed_cycles * self._syscon.cpu_prescaler
        # counts since T was set
        elapsed_counts = int(elapsed_clks / self._prescaler)
        # update T value and epoch
        self._t = (self._t + elapsed_counts) % 0x10000
        self._t_epoch = self.current_cycle

    def _stop_counting(self):
        self.callback_cancel('tovf')

    def _start_counting(self):
        self.callback_after(self._remaining_cycles, 'tovf', self._overflow_callback)
        self._t_epoch = self.current_cycle

    def _overflow_callback(self):
        self._t = self._rcap
        if (self._tcon & 0x30) == 0:
            self._tcon |= 0x80
        self._start_counting()
        self._update_ipl()


class P90Watchdog(Device):

    def __init__(self, args, address):
        super(P90Watchdog, self).__init__(args=args,
                                          name='P90Watchdog',
                                          address=address)
        self.add_registers([
            ('WDTIM', 0x01, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_wdtim),
            ('WDCON', 0x03, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_wdcon),

            ('WDTIM', 0x01, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_wdtim),
            ('WDCON', 0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_wdcon),
        ])
        self.reset()

    def _read_wdtim(self):
        return self._wdtim

    def _read_wdcon(self):
        return self._wdcon

    def _write_wdtim(self, value):
        if self._wdcon == 0x5a:
            self._wdtim = value
            self._wdcon = 0

    def _write_wdcon(self, value):
        self._wdcon = value
        self.running = True

    def tick(self):
        # get cycle count, work out what self._wdtim should be
        # if overflow, reset
        pass

    def reset(self):
        self._wdtim = 0
        self._wdcon = 0xa5
        self._running = False


# class P90GPIO(Device):
#
#    REG_GPP = 0x01
#    REG_GP = 0x03
#
#    _registers = {
#        'GPP': 0x01,
#        'GP': 0x03,
#    }
#
#    def __init__(self, args, address):
#        super(P90GPIO, self).__init__(args=args,
#                                      name='P90GPIO',
#                                      address=address)
#        self.map_registers(P90GPIO._registers)
#        self.reset()
#        self.trace('init done')
#
#    def read(self, width, offset):
#        if width == MEM_SIZE_8:
#            if offset == REG_GPP:
#                return self._gpp | self._gp
#            elif offset == REG_GP:
#                return self._gp
#        return 0
#
#    def write(self, width, offset, value):
#        if width == MEM_SIZE_8:
#            if offset == REG_GPP:
#                self._gpp = value
#            elif offset == REG_GP:
#                self._gp = value
#
#    def reset(self):
#        self._gpp = 0
#        self._gp = 0
#
#

class P90AUX(Device):
    def __init__(self, args, address):
        super(P90AUX, self).__init__(args=args,
                                     name='P90AUX',
                                     address=address)
        self.add_registers([
            ('APP',     0x01, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_app),
            ('APCON',   0x03, m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_apcon),

            ('APP',     0x01, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_app),
            ('APCON',   0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_apcon),
        ])
        self._callback = None
        self.reset()

    def _read_app(self):
        return self._app

    def _read_apcon(self):
        return self._apcon

    def _write_app(self, value):
        self._app = value
        self._notify()

    def _write_apcon(self, value):
        self._apcon = value
        self._notify()

    def reset(self):
        self._app = 0
        self._apcon = 0
        self._notify()

    def _notify(self):
        if self._callback is not None:
            self._callback(app=self._app, apcon=self._apcon)

    def set_callback(self, callback):
        self._callback = callback
