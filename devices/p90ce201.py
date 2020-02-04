import sys
from device import Device
from collections import deque
from musashi.m68k import (
    M68K_IRQ_SPURIOUS,
    M68K_IRQ_AUTOVECTOR,
    MEM_SIZE_8,
)

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


def add_arguments(parser, default_console_port='none', default_crystal_frequency=24):
    parser.add_argument('--p90-console-port',
                        type=str,
                        choices=['0', 'none'],
                        default=default_console_port,
                        metavar='PORT-NUMBER',
                        help='P90CE201 UART port to treat as the console')
    parser.add_argument('--p90-crystal-frequency',
                        type=int,
                        choices=range(1, 24),
                        default=default_crystal_frequency,
                        metavar='FREQUENCY-MHZ',
                        help='P90CE201 clock crystal frequency')


def add_devices(args, emu):
    emu.add_device(args,
                   P90Syscon,
                   address=ADDR_P90Syscon)
#    emu.add_device(args,
#                   P90ICU,
#                   address=ADDR_P90ICU)
#    emu.add_device(args,
#                   P90I2C,
#                   address=ADDR_P90I2C1)
#    emu.add_device(args,
#                   P90I2C,
#                   address=ADDR_P90I2C2)
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
    emu.add_device(args,
                   P90GPIO,
                   address=ADDR_P90GPIO)
    emu.add_device(args,
                   P90AUX,
                   address=ADDR_P90AUX)


class P90Syscon(Device):

    REG_SYSCON1 = 0x00
    REG_SYSCON1H = 0x00
    REG_SYSCON1L = 0x01
    REG_SYSCON2 = 0x02
    REG_SYSCON2H = 0x02
    REG_SYSCON2L = 0x03

    _registers = {
        'SYSCON1H': 0x00,
        'SYSCON1L': 0x01,
        'SYSCON2H': 0x02,
        'SYSCON2L': 0x03,
    }

    def __init__(self, args, address, interrupt):
        super(P90Syscon, self).init(args=args,
                                    name='P90Syscon',
                                    address=address)
        self.map_registers(P90Syscon._registers)
        self.reset()
        self.trace('init done')

        self._fXTAL = args.p90_crystal_frequency

    def read(self, width, offset):
        if width == MEM_SIZE_16:
            if offset == REG_SYSCON1:
                return P90Syscon.syscon1
            elif offset == REG_SYSCON2:
                return P90Syscon.syscon2
        elif width == MEM_SIZE_8:
            if offset == REG_SYSCON1H:
                return P90Syscon.syscon1 >> 8
            elif offset == REG_SYSCON1L:
                return P90Syscon.syscon1 & 0xff
            elif offset == REG_SYSCON2H:
                return P90Syscon.syscon2 >> 8
            elif offset == REG_SYSCON2L:
                return P90Syscon.syscon2 & 0xff
        return 0

    def write(self, width, offset, value):
        if width == MEM_SIZE_16:
            if offset == REG_SYSCON1:
                P90Syscon.syscon1 = value
            elif offset == REG_SYSCON2:
                P90Syscon.syscon2 = value
        elif width == MEM_SIZE_8:
            if offset == REG_SYSCON1H:
                P90Syscon.syscon1 = (P90Syscon.syscon1 & 0xff) + (value << 8)
            elif offset == REG_SYSCON1L:
                P90Syscon.syscon1 = (P90Syscon.syscon1 & 0xff00) + (value & 0xff)
            elif offset == REG_SYSCON2H:
                P90Syscon.syscon2 = (P90Syscon.syscon2 & 0xff) + (value << 8)
            elif offset == REG_SYSCON2L:
                P90Syscon.syscon2 = (P90Syscon.syscon2 & 0xff00) + (value & 0xff)

    def reset(self):
        P90Syscon.syscon1 = 0x0000
        P90Syscon.syscon2 = 0x0004

    @classmethod
    def t0_divisor(cls):
        if P90Syscon.syscon2 & (0x0010):
            return 32
        else:
            return 2

    @classmethod
    def t1_divisor(cls):
        if P90Syscon.syscon2 & (0x0002):
            return 32
        else:
            return 2

    @classmethod
    def t2_divisor(cls):
        if P90Syscon.syscon2 & (0x0400):
            return P90Syscon.bpclk_divisor() * 4
        else:
            return 2

    @classmethod
    def bpclk_divisor(cls):
        sel = (P90Syscon.syscon2 >> 8) & 3
        if sel == 0:
            return 3
        elif sel == 1:
            return 2.5
        elif sel == 2:
            return 2
        elif sel == 3:
            return 1.5


class P90ICU(Device):

    REG_LIR7 = 0x01
    REG_LIV7 = 0x03
    REG_LIR6 = 0x05
    REG_LIV6 = 0x07
    REG_LIR5 = 0x09
    REG_LIV5 = 0x0b
    REG_LIR4 = 0x0d
    REG_LIV4 = 0x0f
    REG_LPCRH = 0x11
    REG_LPPH = 0x13
    REG_LIR3 = 0x21
    REG_LIV3 = 0x23
    REG_LIR2 = 0x25
    REG_LIV2 = 0x27
    REG_LIR1 = 0x29
    REG_LIV1 = 0x2b
    REG_LIR0 = 0x2d
    REG_LIV0 = 0x2f
    REG_LPCRL = 0x31
    REG_LPPL = 0x33

    _registers = {
        'LIR7': 0x01,
        'LIV7': 0x03,
        'LIR6': 0x05,
        'LIV6': 0x07,
        'LIR5': 0x09,
        'LIV5': 0x0b,
        'LIR4': 0x0d,
        'LIV4': 0x0f,
        'LPCRH': 0x11,
        'LPPH': 0x13,
        'LIR3': 0x21,
        'LIV3': 0x23,
        'LIR2': 0x25,
        'LIV2': 0x27,
        'LIR1': 0x29,
        'LIV1': 0x2b,
        'LIR0': 0x2d,
        'LIV0': 0x2f,
        'LPCRL': 0x31,
        'LPPL': 0x33,
    }

    def __init__(self, args, address, interrupt):
        super(P90ICU, self).init(args=args,
                                 name='P90ICU',
                                 address=address)
        self.map_registers(P90ICU._registers)
        self.reset()
        self.trace('init done')

    def read(self, width, offset):
        return 0

    def write(self, width, offset, value):
        pass

    def tick(self):
        pass

    def reset(self):
        pass

    def get_interrupt(self):
        return 0


class P90I2C(Device):

    REG_SDAT = 0x01
    REG_SADR = 0x03
    REG_SSTA = 0x05
    REG_SSCON = 0x07
    REG_SIR = 0x09
    REG_SIV = 0x0b

    _registers = {
        'SDAT': 0x01,
        'SADR': 0x03,
        'SSTA': 0x05,
        'SSCON': 0x07,
        'SIR': 0x09,
        'SIV': 0x0b,
    }

    def __init__(self, args, address, interrupt):
        super(P90I2C, self).init(args=args,
                                 name='P90I2C',
                                 address=address)
        self.map_registers(P90I2C._registers)
        self.reset()
        self.trace('init done')

    def read(self, width, offset):
        return 0

    def write(self, width, offset, value):
        pass

    def tick(self):
        pass

    def reset(self):
        pass

    def get_interrupt(self):
        return 0


class P90UART(Device):

    REG_SBUF = 0x01
    REG_SCON = 0x03
    REG_URIR = 0x05
    REG_URIV = 0x07
    REG_UTIR = 0x09
    REG_UTIV = 0x0b

    _registers = {
        'SBUF': 0x01,
        'SCON': 0x03,
        'URIR': 0x05,
        'URIV': 0x07,
        'UTIR': 0x09,
        'UTIV': 0x0b,
    }

    def __init__(self, args, address, interrupt):
        super(P90UART, self).init(args=args,
                                  name='P90UART',
                                  address=address)
        self.map_registers(P90UART._registers)
        self.reset()
        self.trace('init done')
        self._is_console = (args.p90_console_port == '0')
        if self._is_console:
            self.register_console_input_handler(self._handle_console_input)

    def read(self, width, offset):
        if width == MEM_SIZE_8:
            if offset == REG_SBUF:
                if len(self._rxfifo) > 0:
                    value = self._rxfifo.popleft()
                    self._update_status()
                else:
                    value = 0xff
            elif offset == REG_SCON:
                return self._scon
            elif offset == REG_URIR:
                return self._urir
            elif offset == REG_URIV:
                return self._uriv
            elif offset == REG_UTIR:
                return self._utir
            elif offset == REG_UTIV:
                return self._utiv

        return 0

    def write(self, width, offset, value):
        if width == MEM_SIZE_8:
            if offset == REG_SBUF:
                if self._is_console:
                    self.console_handle.output(chr(value).encode('latin-1'))
                if self._scon & 0x02 == 0:
                    # XXX should be based on time-since-write
                    self._scon |= 0x02  # transmit complete status
                    self._utir |= 0x08  # interrupt pending

            elif offset == REG_SCON:
                self._scon = value
            elif offset == REG_URIR:
                self._urir = value
            elif offset == REG_URIV:
                self._uriv = value
            elif offset == REG_UTIR:
                self._utir = value
            elif offset == REG_UTIV:
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

    def _update_status(self):
        if len.(self._rxfifo) > 0:
            self._scon |= 0x01
            self._urir |= 0x08

    def _handle_console_input(self, input):
        if self._scon & (1 << 4):
            for c in input:
                self._rxfifo.append(c)
                self._update_status()


class P90Timer(Device):

    REG_T = 0x00
    REG_RCAP = 0x02
    REG_TCON = 0x05
    REG_TIR = 0x07
    REG_TIV = 0x09

    _registers = {
        'TH': 0x00,
        'TL': 0x01,
        'RCAPH': 0x02,
        'RCAPL': 0x03,
        'TCON': 0x05,
        'TIR': 0x07,
        'TIV': 0x09,
    }

    def __init__(self, args, address, interrupt):
        super(P90Timer, self).init(args=args,
                                   name='P90Timer',
                                   address=address)
        self.map_registers(P90Timer._registers)
        self.reset()
        self.trace('init done')
        if address == ADDR_P90Timer0:
            self._divisor = P90Syscon.t0_rate
        elif address == ADDR_P90Timer1:
            self._divisor = P90Syscon.t1_rate
        elif address == ADDR_P90Timer2:
            self._divisor = P90Syscon.t2_rate

    def read(self, width, offset):
        if width == MEM_SIZE_16:
            if offset == REG_T:
                self._update_state()
                return self._t
                pass
            elif offset == REG_RCAP:
                return self._rcap
        elif width == MEM_SIZE_8:
            if offset == REG_TCON:
                return self._tcon
            elif offset == REG_TIR:
                return self._tir
            elif offset == REG_TIV:
                return self._tiv
        return 0

    def write(self, width, offset, value):
        if width == MEM_SIZE_16:
            if offset == REG_T:
                self._t = value
                self._update_state(reload=True)
                pass
            elif offset == REG_RCAP:
                self._rcap = value
                self._update_state(reload=True)
        elif width == MEM_SIZE_8:
            if offset == REG_TCON:
                self._tcon = value
                self._update_state(reload=True)
            elif offset == REG_TIR:
                self._tir = value
            elif offset == REG_TIV:
                self._tiv = value

    def tick(self):
        self._update_state()    
        if self._is_counting():
            return (0x10000 - self._t) * self.divisor()

    def reset(self):
        self._t = 0
        self._rcap = 0
        self._tir = 0
        self._tiv = 0
        self._epoch_cycle = self.current_cycle()
        self._last_interrupt_cycle = self._epoch_cycle

    def get_interrupt(self):
        if ((self._tir & 0x0f) > 0x08):
            return self._tir & 7
        return 0

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            if (self._tir & 0x08):
                self._tir &= ~0x08
                if (self._tir & 0x20):
                    return self._tiv
                else:
                    return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS

    def _is_counting(self):
        return (self._tcon & 0x06) == 0x04

    def _update_state(self, reload=False):
        #
        # The timer counts up from either zero or RCAP and
        # interrupts at overflow. Since thinking about this
        # makes my brain hurt, pretend that it counts up from
        # zero to RCAP / 0x10000 and adjust the register
        # contents accordingly.
        #
        if self._is_counting():
            if (self._tcon & 0x31) == 0x01:
                period = 0x10000
            else:
                period = 0x10000 - self._rcap

            current_cycle = self.current_cycle()

            if reload:
                # note that this actually ignores the value written to T.
                # If we cared, we could account for it in setting the epoch, but
                # it's probably safe just to pretend they wrote zero / RCAP...
                self._epoch_cycle = current_cycle
                self._last_interrupt_cycle = current_cycle

            current_count = int((current_cycle - self._epoch_cycle) / self.divisor())
            self._t = ((current_count % period) + period) & 0xffff

            if current_count > (self._last_interrupt_cycle + period):
                self._last_interrupt_cycle = current_cycle
                if (self._tcon & 0x30) == 0x00:
                    self._tcon |= 0x80
                    self._tir |= 0x08


class P90Watchdog(Device):

    REG_WDTIM = 0x01
    REG_WDCON = 0x03

    _registers = {
        'WDTIM': 0x01,
        'WDCON': 0x03,
    }

    def __init__(self, args, address, interrupt):
        super(P90Watchdog, self).init(args=args,
                                      name='P90Watchdog',
                                      address=address)
        self.map_registers(P90Watchdog._registers)
        self.reset()
        self.trace('init done')

    def read(self, width, offset):
        if width == MEM_SIZE_8:
            if offset == REG_WDTIM:
                return self._wdtim
            elif offset == REG_WDCON:
                return self._wdcon

        return 0

    def write(self, width, offset, value):
        if width == MEM_SIZE_8:
            if offset == REG_WDTIM:
                if self._wdcon == 0x5a:
                    self._wdtim = value
                    self._wdcon = 0
            elif offset == REG_WDCON:
                self._wdcon = value
                self.running = True
        pass

    def tick(self):
        # get cycle count, work out what self._wdtim should be
        # if overflow, reset
        pass

    def reset(self):
        self._wdtim = 0
        self._wdcon = 0xa5
        self._running = False


class P90GPIO(Device):

    REG_GPP = 0x01
    REG_GP = 0x03

    _registers = {
        'GPP': 0x01,
        'GP': 0x03,
    }

    def __init__(self, args, address, interrupt):
        super(P90GPIO, self).init(args=args,
                                  name='P90GPIO',
                                  address=address)
        self.map_registers(P90GPIO._registers)
        self.reset()
        self.trace('init done')

    def read(self, width, offset):
        if width == MEM_SIZE_8:
            if offset == REG_GPP:
                return self._gpp | self._gp
            elif offset == REG_GP:
                return self._gp
        return 0

    def write(self, width, offset, value):
        if width == MEM_SIZE_8:
            if offset == REG_GPP:
                self._gpp = value
            elif offset == REG_GP:
                self._gp = value

    def reset(self):
        self._gpp = 0
        self._gp = 0


class P90AUX(Device):

    REG_APP = 0x01
    REG_APCON = 0x03

    _registers = {
        'APP': 0x01,
        'APCON': 0x03,
    }

    def __init__(self, args, address, interrupt):
        super(P90AUX, self).init(args=args,
                                 name='P90AUX',
                                 address=address)
        self.map_registers(P90AUX._registers)
        self.reset()
        self.trace('init done')

    def read(self, width, offset):
        if width = MEM_SIZE_8:
            if offset == REG_APP:
                return self._app | self._apcon
            elif offset == REG_APCON:
                return self._apcon
        return 0

    def write(self, width, offset, value):
        if width = MEM_SIZE_8:
            if offset == REG_APP:
                self._app = value
            elif offset == REG_APCON:
                self._apcon = value

    def reset(self):
        self._app = 0
        self._apcon = 0
