import sys
from device import Device
from collections import deque
from musashi.m68k import (
    MEM_SIZE_8,
)


class Channel():

    REG_MR = 0x01
    REG_SR = 0x03
    REG_RB = 0x07
    REG_CSR = 0x03
    REG_CR = 0x05
    REG_TB = 0x07

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
            return = self._mr2
        else:
            self._mrAlt = True
            return = self._mr1

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


class Counter():

    MODE_MASK = 0x70
    MODE_CTR_TXCA = 0x10
    MODE_CTR_TXCB = 0x20
    MODE_CTR_XTAL16 = 0x30
    MODE_TMR_XTAL = 0x60
    MODE_TMR_XTAL16 = 0x70
    MODE_TMR = 0x40

    def __init__(self, parent):
        self._parent = parent
        self._reload = 0x0001
        self._interrupting = False
        self._running = False
        self._timer_deadline = 0

        self.set_mode(Counter.MODE_TMR_XTAL16)
        self._timer_epoch = self._parent.current_cycle

    def read_cur(self):
        self._update_status()
        return self._count >> 8

    def read_clr(self):
        self._update_status()
        return self._count & 0xff

    def read_startcc(self):
        if self._mode_is_counter:
            self._running = True
            self._counter_deadline = self._parent.current_cycle + self._reload * self._prescale
        else:
            self._timer_epoch = self._parent.current_cycle
            self._timer_deadline = self._timer_epoch + self._timer_period
        return 0xff

    def read_stopcc(self):
        if self._mode_is_counter:
            self._update_status()
            self._running = False
        else:
            current_cycle = self._parent.current_cycle
            last_interrupt_cycle = current_cycle - (current_cycle % self._timer_period)
            self._timer_deadline = last_interrupt_cycle + self._timer_period
        self._interrupting = False
        return 0xff

    def write_acr(self, value):
        mode = value & Counter.MODE_MASK
        cycle_ratio = self._parent.cycle_rate / 3686400.0

        if (mode == Counter.MODE_CTR_TXCA) or (mode == Counter.MODE_CTR_TXCB):
            self._prescale = cycle_ratio * 96     # assume 38400bps
        elif mode == Counter.MODE_CTR_XTAL16:
            self._prescale = cycle_ratio * 16
        elif mode == Counter.MODE_TMR_XTAL:
            self._prescale = cycle_ratio * 1
        elif mode == Counter.MODE_TMR_XTAL16:
            self._prescale = cycle_ratio * 16
        else:
            raise RuntimeError('timer mode 0x{:02x} not supported'.format(mode))

        self._mode = mode

    def tick(self):
        return self._update_status()

    def write_ctlr(self, value):
        self._reload = (self._reload & 0xff00) | value

    def write_ctur(self, value):
        self._reload = (self._reload & 0x00ff) | (value << 8)

    def _update_status(self):
        ret = None
        current_cycle = self._parent.current_cycle
        if self._mode_is_counter:
            if current_cycle < self._counter_deadline:
                cycles_remaining = self._counter_deadline - current_cycle
                self._count = cycles_remaining / self._prescale
                ret = int(cycles_remaining)
            else:
                cycles_past = current_cycle - self._counter_deadline
                self._count = 0xffff - int((cycles_past / self._prescale) % 0x10000)
                self._interrupting = True
        else:
            counts_elapsed = int((current_cycle - self._timer_epoch) / self._prescale)
            self._count = self._reload - int(counts_elapsed % (self._reload + 1))

            if current_cycle > self._timer_deadline:
                self._interrupting = True
                ret = self._timer_period
            else:
                ret = self._timer_deadline - current_cycle
        return ret

    @property
    def is_interrupting(self):
        self._update_status()
        return self._interrupting

    @property
    def _mode_is_counter(self):
        return not self._mode_is_timer

    @property
    def _mode_is_timer(self):
        return self._mode & Counter.MODE_TMR

    @property
    def _timer_period(self):
        return 2 * self._reload * self._prescale


class MC68681(Device):
    """
    Emulation of the MC68681 DUART / timer device.
    """

    # assuming the device is mapped to the low byte

    REG_SELMASK = 0x18
    REG_SEL_A = 0x00
    REG_SEL_B = 0x10

    # non-channel registers
    REG_IPCR = 0x09
    REG_ACR = 0x09
    REG_ISR = 0x0b
    REG_IMR = 0x0b
    REG_CUR = 0x0d
    REG_CTUR = 0x0d
    REG_CLR = 0x0f
    REG_CTLR = 0x0f
    REG_IVR = 0x19
    REG_IPR = 0x1b
    REG_OPCR = 0x1b
    REG_STARTCC = 0x1d
    REG_OPRSET = 0x1d
    REG_STOPCC = 0x1f
    REG_OPRCLR = 0x1f

    _registers = {
        'MRA': 0x01,
        'SRA/CSRA': 0x03,
        'CRA': 0x05,
        'RBA/TBA': 0x07,
        'IPCR/ACR': 0x09,
        'ISR/IMR': 0x0b,
        'CUR/CTUR': 0x0d,
        'CLR/CTLR': 0x0f,
        'MRB': 0x11,
        'SRB/CSRB': 0x13,
        'RBB/TBB': 0x17,
        'IVR': 0x19,
        'IPR/OPCR': 0x1b,
        'STARTCC/OPRSET': 0x1d,
        'STOPCC/OPRCLR': 0x1f
    }

    def __init__(self, args, address, interrupt):
        super(MC68681, self).__init__(args=args,
                                      name='MC68681',
                                      address=address,
                                      interrupt=interrupt)

        self._a = Channel(self, args.duart_console_port == 'A')
        self._b = Channel(self, args.duart_console_port == 'B')
        self._counter = Counter(self)
        self.add_registers([
            ('MRA',            0x01, MEM_SIZE_8, self._a.read_mr,            self._a.write_mr),
            ('SRA/CSRA',       0x03, MEM_SIZE_8, self._a.read_sr,            self._a.write_csr),
            ('CRA',            0x05, MEM_SIZE_8, self._a.read_cr,            self._a.write_cr),
            ('RBA/TBA',        0x07, MEM_SIZE_8, self._a.read_rb,            self._a.write_tb),
            ('IPCR/ACR',       0x09, MEM_SIZE_8, self._read_ipcr,            self._counter.write_acr),
            ('ISR/IMR',        0x0b, MEM_SIZE_8, self._read_isr,             self._write_imr),
            ('CUR/CTUR',       0x0d, MEM_SIZE_8, self._counter.read_cur,     self._counter.write_ctur),
            ('CLR/CTLR',       0x0f, MEM_SIZE_8, self._counter.read_clr,     self._counter.write_ctlr),
            ('MRB',            0x11, MEM_SIZE_8, self._b.read_mr,            self._b.write_mr),
            ('SRB/CSRB',       0x13, MEM_SIZE_8, self._b.read_sr,            self._b.write_csr),
            ('CRB',            0x15, MEM_SIZE_8, self._b.read_cr,            self._b.write_cr),
            ('RBB/TBB',        0x17, MEM_SIZE_8, self._b.read_rb,            self._b.write_tb),
            ('IVR',            0x19, MEM_SIZE_8, self._read_ivr,             self._write_ivr),
            ('IPR/OPCR',       0x1b, MEM_SIZE_8, self._read_ipr,             self._write_nop),
            ('STARTCC/OPRSET', 0x1d, MEM_SIZE_8, self._counter.read_startcc, self._write_nop),
            ('STOPCC/OPRCLR',  0x1f, MEM_SIZE_8, self._counter.read_stopcc,  self._write_nop),
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
        self._update_status()
        return self._isr

    def _read_ivr(self):
        return self._ivr

    def _read_ipr(self):
        return 0x03  # CTSA/CTSB are always asserted

    def _write_imr(self, value):
        self._imr = value
        # XXX interrupt status may have changed...

    def _write_ivr(self, value):
        self._ivr = value

    def _write_nop(self, value):
        pass

    def tick(self):
        cq = self._counter.tick()
        aq = self._a.tick()
        bq = self._b.tick()

        for q in [cq, aq, bq].sorted():
            if q > 0:
                break
        return q

    def reset(self):
        self._a.reset()
        self._b.reset()
        self._isr = 0
        self._imr = 0
        self._ivr = 0xf
        self._count = 0
        self._countReload = 0xffff

    def get_interrupt(self):
        self._update_status()
        if self._isr & self._imr:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            if self._isr & self._imr:
                return self._ivr
        return M68K_IRQ_SPURIOUS

    def _update_status(self):
        self._isr &= ~0x3b
        if self._counter.is_interrupting:
            self._isr |= 0x08
        self._isr |= self._a.get_interrupts()
        self._isr |= self._b.get_interrupts() << 4
