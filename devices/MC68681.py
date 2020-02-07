import sys
from device import Device
from collections import deque

from musashi import m68k


class Channel():

    MR1_FFULL_EN = 0x40

    CTRL_CMD_MASK = 0xf0
    CTRL_BRKSTOP = 0x70
    CTRL_BRKSTART = 0x60
    CTRL_BRKRST = 0x50
    CTRL_ERRST = 0x40
    CTRL_TXRST = 0x30
    CTRL_RXRST = 0x20
    CTRL_MRRST = 0x10
    CTRL_TXDIS = 0x08
    CTRL_TXEN = 0x04
    CTRL_RXDIS = 0x02
    CTRL_RXEN = 0x01

    STATUS_RECEIVED_BREAK = 0x80
    STATUS_FRAMING_ERROR = 0x40
    STATUS_PARITY_ERROR = 0x20
    STATUS_OVERRUN_ERROR = 0x10
    STATUS_TRANSMITTER_EMPTY = 0x08
    STATUS_TRANSMITTER_READY = 0x04
    STATUS_FIFO_FULL = 0x02
    STATUS_RECEIVER_READY = 0x01

    INT_TXRDY = 0x01
    INT_RXRDY_FFULL = 0x02

    def __init__(self, parent, is_console=False):
        self.reset()
        self._parent = parent
        self._is_console = is_console
        if self._is_console:
            self._parent.register_console_input_handler(self._handle_console_input)

    def reset(self):
        self._mr1 = 0
        self._mr2 = 0
        self._mrAlt = False
        self._sr = 0
        self._rxfifo = deque()
        self._rxEnable = False
        self._txEnable = False

    def read_mr(self):
        if self._mrAlt:
            return self._mr2
        else:
            self._mrAlt = True
            return self._mr1

    def read_sr(self):
        return self._sr

    def read_rb(self):
        value = 0xff
        if len(self._rxfifo) > 0:
            value = self._rxfifo.popleft()
        return value

    def write_mr(self, value):
        if self._mrAlt:
            self._mr2 = value
        else:
            self._mrAlt = True
            self._mr1 = value

    def write_csr(self, value):
        pass

    def write_cr(self, value):
        # rx/tx dis/enable logic
        if value & Channel.CTRL_RXDIS:
            self._rxEnable = False
        elif value & Channel.CTRL_RXEN:
            self._rxEnable = True
        if value & Channel.CTRL_TXDIS:
            self._txEnable = False
        elif value & Channel.CTRL_TXEN:
            self._txEnable = True

        cmd = value & Channel.CTRL_CMD_MASK
        if cmd == Channel.CTRL_MRRST:
            self._mrAlt = False
        elif cmd == Channel.CTRL_RXRST:
            self._rxEnable = False
            self._rxfifo.clear()
        elif cmd == Channel.CTRL_TXRST:
            self._txEnable = False
            # self._txfifo

    def write_tb(self, value):
        self._parent.console_handle_output(chr(value).encode('latin-1'))

    def tick(self):
        return self._update_status()

    def _update_status(self):
        # transmitter is always ready
        self._sr = Channel.STATUS_TRANSMITTER_EMPTY | Channel.STATUS_TRANSMITTER_READY

        # rx is ready or full depending on fifo occupancy
        rxcount = len(self._rxfifo)
        if rxcount > 0:
            self._sr |= Channel.STATUS_RECEIVER_READY
            if (rxcount > 2):
                self._sr |= Channel.STATUS_FIFO_FULL
        return 0

    def get_interrupts(self):
        """
        return possible interrupts (unmasked)
        """
        interrupts = 0
        if self._sr & Channel.STATUS_TRANSMITTER_READY:
            interrupts |= Channel.INT_TXRDY

        if self._mr1 & Channel.MR1_FFULL_EN:
            if self._sr & Channel.STATUS_FIFO_FULL:
                interrupts |= Channel.INT_RXRDY_FFULL
        elif self._sr & Channel.STATUS_RECEIVER_READY:
            interrupts |= Channel.INT_RXRDY_FFULL

        return interrupts

    def _handle_console_input(self, input):
        for c in input:
            self._rxfifo.append(c)


class MC68681(Device):
    """
    Emulation of the MC68681 DUART / timer device.
    """

    # assuming the device is mapped to the low byte

    REG_SELMASK = 0x18
    REG_SEL_A = 0x00
    REG_SEL_B = 0x10

    IMR_COUNTER = 0x08

    MODE_MASK = 0x70
    MODE_CTR_TXCA = 0x10
    MODE_CTR_TXCB = 0x20
    MODE_CTR_XTAL16 = 0x30
    MODE_TMR_XTAL = 0x60
    MODE_TMR_XTAL16 = 0x70
    MODE_TMR = 0x40

    def __init__(self, args, address, interrupt):
        super(MC68681, self).__init__(args=args,
                                      name='MC68681',
                                      address=address,
                                      interrupt=interrupt)

        self._a = Channel(self, args.duart_console_port == 'A')
        self._b = Channel(self, args.duart_console_port == 'B')
        self.add_registers([
            ('MRA',            0x01, m68k.MEM_SIZE_8, self._a.read_mr,    self._a.write_mr),
            ('SRA/CSRA',       0x03, m68k.MEM_SIZE_8, self._a.read_sr,    self._a.write_csr),
            ('CRA',            0x05, m68k.MEM_SIZE_8, self._read_nop,     self._a.write_cr),
            ('RBA/TBA',        0x07, m68k.MEM_SIZE_8, self._a.read_rb,    self._a.write_tb),
            ('IPCR/ACR',       0x09, m68k.MEM_SIZE_8, self._read_ipcr,    self._write_acr),
            ('ISR/IMR',        0x0b, m68k.MEM_SIZE_8, self._read_isr,     self._write_imr),
            ('CUR/CTUR',       0x0d, m68k.MEM_SIZE_8, self._read_cur,     self._write_ctur),
            ('CLR/CTLR',       0x0f, m68k.MEM_SIZE_8, self._read_clr,     self._write_ctlr),
            ('MRB',            0x11, m68k.MEM_SIZE_8, self._b.read_mr,    self._b.write_mr),
            ('SRB/CSRB',       0x13, m68k.MEM_SIZE_8, self._b.read_sr,    self._b.write_csr),
            ('CRB',            0x15, m68k.MEM_SIZE_8, self._read_nop,     self._b.write_cr),
            ('RBB/TBB',        0x17, m68k.MEM_SIZE_8, self._b.read_rb,    self._b.write_tb),
            ('IVR',            0x19, m68k.MEM_SIZE_8, self._read_ivr,     self._write_ivr),
            ('IPR/OPCR',       0x1b, m68k.MEM_SIZE_8, self._read_ipr,     self._write_nop),
            ('STARTCC/OPRSET', 0x1d, m68k.MEM_SIZE_8, self._read_startcc, self._write_nop),
            ('STOPCC/OPRCLR',  0x1f, m68k.MEM_SIZE_8, self._read_stopcc,  self._write_nop),
        ])
        self.reset()

    @classmethod
    def add_arguments(cls, parser, default_console_port='none'):
        parser.add_argument('--duart-console-port',
                            type=str,
                            choices=['A', 'B', 'none'],
                            default=default_console_port,
                            help='MC68681 DUART port to treat as console')
        return

    def _read_ipcr(self):
        return 0x03  # CTSA/CTSB are always asserted

    def _read_isr(self):
        self.tick()
        return self._isr

    def _read_ivr(self):
        return self._ivr

    def _read_ipr(self):
        return 0x03  # CTSA/CTSB are always asserted

    def _read_cur(self):
        self._update_counter()
        return self._count >> 8

    def _read_clr(self):
        self._update_counter()
        return self._count & 0xff

    def _read_startcc(self):
        if self._mode_is_counter:
            self._counter_running = True
            self._counter_interrupting = False
            self._counter_deadline = self.current_cycle + self._reload * self._prescale
        else:
            self._timer_epoch = self.current_cycle
            self._timer_deadline = self._timer_epoch + self._timer_period

        return 0xff

    def _read_stopcc(self):
        if self._mode_is_counter:
            self._update_counter()
            self._counter_running = False
        else:
            current_cycle = self.current_cycle
            last_interrupt_cycle = current_cycle - (current_cycle % self._timer_period)
            self._timer_deadline = last_interrupt_cycle + self._timer_period

        self._counter_interrupting = False
        return 0xff

    def _read_nop(self):
        pass

    def _write_imr(self, value):
        self._imr = value
        # XXX interrupt status may have changed...

    def _write_ivr(self, value):
        self._ivr = value

    def _write_acr(self, value):
        mode = value & self.MODE_MASK
        cycle_ratio = self.cycle_rate / 3686400.0

        if (mode == self.MODE_CTR_TXCA) or (mode == self.MODE_CTR_TXCB):
            self._prescale = cycle_ratio * 96     # assume 38400bps
        elif mode == self.MODE_CTR_XTAL16:
            self._prescale = cycle_ratio * 16
        elif mode == self.MODE_TMR_XTAL:
            self._prescale = cycle_ratio * 1
        elif mode == self.MODE_TMR_XTAL16:
            self._prescale = cycle_ratio * 16
        else:
            raise RuntimeError('timer mode 0x{:02x} not supported'.format(mode))

        self._mode = mode

    def _write_ctlr(self, value):
        self._reload = (self._reload & 0xff00) | value

    def _write_ctur(self, value):
        self._reload = (self._reload & 0x00ff) | (value << 8)

    def _write_nop(self, value):
        pass

    def tick(self):
        self._isr &= ~0x3b

        self._a.tick()
        self._isr |= self._a.get_interrupts()
        self._b.tick()
        self._isr |= self._b.get_interrupts() << 4

        counter_quantum = self._update_counter()
        if self._counter_interrupting:
            self._isr |= 0x08

        if self._imr & self.IMR_COUNTER:
            return counter_quantum
        return 0

    def reset(self):
        self._a.reset()
        self._b.reset()
        self._isr = 0
        self._imr = 0
        self._ivr = 0xf
        self._reload = 0x0001
        self._counter_interrupting = False
        self._counter_running = False
        self._timer_deadline = 0
        self._write_acr(self.MODE_TMR_XTAL16)
        self._timer_epoch = self.current_cycle

    def get_interrupt(self):
        if self._is_interrupting:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if (interrupt == self._interrupt) and self._is_interrupting:
            return self._ivr
        return m68k.IRQ_SPURIOUS

    def _update_counter(self):
        self.tick_deadline = 0
        current_cycle = self.current_cycle
        if self._mode_is_counter:
            if self._counter_running:
                if current_cycle < self._counter_deadline:
                    cycles_remaining = self._counter_deadline - current_cycle
                    self._count = cycles_remaining / self._prescale
                    self.tick_deadline = self._counter_deadline
                else:
                    cycles_past = current_cycle - self._counter_deadline
                    self._count = 0xffff - ((cycles_past / self._prescale) % 0x10000)
                    self._counter_interrupting = True
        else:
            counts_elapsed = int((current_cycle - self._timer_epoch) / self._prescale)
            self._count = self._reload - (counts_elapsed % (self._reload + 1))

            if current_cycle > self._timer_deadline:
                self._counter_interrupting = True
            else:
                self.tick_deadline = self._timer_deadline

    @property
    def _is_interrupting(self):
        return (self._isr & self._imr) != 0

    @property
    def is_counter_interrupting(self):
        self._update_status()
        return self._counter_interrupting

    @property
    def _mode_is_counter(self):
        return not self._mode_is_timer

    @property
    def _mode_is_timer(self):
        return self._mode & self.MODE_TMR

    @property
    def _timer_period(self):
        return 2 * self._reload * self._prescale
