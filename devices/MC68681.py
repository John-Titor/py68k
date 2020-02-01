import sys
from device import Device
from collections import deque


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

    def read(self, addr):
        # default read result
        value = 0xff

        if addr == Channel.REG_MR:
            if self._mrAlt:
                value = self._mr2
            else:
                self._mrAlt = True
                value = self._mr1

        elif addr == Channel.REG_SR:
            value = self._sr

        elif addr == Channel.REG_RB:
            if len(self._rxfifo) > 0:
                value = self._rxfifo.popleft()

        self.update_status()
        return value

    def write(self, addr, value):

        if addr == Channel.REG_MR:
            if self._mrAlt:
                self._mr2 = value
            else:
                self._mrAlt = True
                self._mr1 = value

        elif addr == Channel.REG_CSR:
            pass

        elif addr == Channel.REG_CR:
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

        elif addr == Channel.REG_TB and self._is_console:
            self._parent.console_handle_output(chr(value).encode('ascii'))

        self.update_status()

    def update_status(self):
        # transmitter is always ready
        self._sr = Channel.STATUS_TRANSMITTER_EMPTY | Channel.STATUS_TRANSMITTER_READY

        rxcount = len(self._rxfifo)
        if rxcount > 0:
            self._sr |= Channel.STATUS_RECEIVER_READY
            if (rxcount > 2):
                self._sr |= Channel.STATUS_FIFO_FULL

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
        self.update_status()
        self._parent.update_status()


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

    def set_mode(self, mode):
        mode &= Counter.MODE_MASK
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

    def set_reload_low(self, value):
        self._reload = (self._reload & 0xff00) | value

    def set_reload_high(self, value):
        self._reload = (self._reload & 0x00ff) | (value << 8)

    def start(self):
        if self._mode_is_counter:
            self._running = True
            self._counter_deadline = self._parent.current_cycle + self._reload * self._prescale
        else:
            self._timer_epoch = self._parent.current_cycle
            self._timer_deadline = self._timer_epoch + self._timer_period

    def stop(self):
        if self._mode_is_counter:
            self._update_state()
            self._running = False
        else:
            current_cycle = self._parent.current_cycle
            last_interrupt_cycle = current_cycle - (current_cycle % self._timer_period)
            self._timer_deadline = last_interrupt_cycle + self._timer_period
        self._interrupting = False

    def get_count(self):
        self._update_state()
        return self._count

    @property
    def is_interrupting(self):
        self._update_state()
        return self._interrupting

    def _update_state(self):
        ret = 0
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

    def tick(self):
        return self._update_state()

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
        self.map_registers(MC68681._registers)

        self._a = Channel(self, args.duart_console_port == 'A')
        self._b = Channel(self, args.duart_console_port == 'B')
        self._counter = Counter(self)
        self.reset()
        self.trace('init done')

    @classmethod
    def add_arguments(cls, parser, default_console_port='none'):
        parser.add_argument('--duart-console-port',
                            type=str,
                            choices=['A', 'B', 'none'],
                            default=default_console_port,
                            help='MC68681 DUART port to treat as console')
        return

    def read(self, width, offset):
        regsel = offset & MC68681.REG_SELMASK
        if regsel == MC68681.REG_SEL_A:
            value = self._a.read(offset - MC68681.REG_SEL_A)

        elif regsel == MC68681.REG_SEL_B:
            value = self._b.read(offset - MC68681.REG_SEL_B)

        elif offset == MC68681.REG_IPCR:
            value = 0x03  # CTSA/CTSB are always asserted

        elif offset == MC68681.REG_ISR:
            value = self._isr

        elif offset == MC68681.REG_CUR:
            value = self._counter.get_count() >> 8

        elif offset == MC68681.REG_CLR:
            value = self._counter.get_count() & 0xff

        elif offset == MC68681.REG_IVR:
            value = self._ivr

        elif offset == MC68681.REG_IPR:
            value = 0x03  # CTSA/CTSB are always asserted

        elif offset == MC68681.REG_STARTCC:
            self._counter.start()
            value = 0xff

        elif offset == MC68681.REG_STOPCC:
            self._counter.stop()
            value = 0xff

        else:
            raise RuntimeError('read from 0x{:02x} not handled'.format(offset))

        self.update_status()
        return value

    def write(self, width, offset, value):
        regsel = offset & MC68681.REG_SELMASK
        if regsel == MC68681.REG_SEL_A:
            self._a.write(offset - MC68681.REG_SEL_A, value)

        elif regsel == MC68681.REG_SEL_B:
            self._b.write(offset - MC68681.REG_SEL_B, value)

        elif offset == MC68681.REG_ACR:
            self._counter.set_mode(value)

        elif offset == MC68681.REG_IMR:
            self._imr = value
            # XXX interrupt status may have changed...

        elif offset == MC68681.REG_CTUR:
            self._counter.set_reload_high(value)

        elif offset == MC68681.REG_CTLR:
            self._counter.set_reload_low(value)

        elif offset == MC68681.REG_IVR:
            self._ivr = value

        elif offset == MC68681.REG_OPCR:
            pass
        elif offset == MC68681.REG_OPRSET:
            pass
        elif offset == MC68681.REG_OPRCLR:
            pass
        else:
            raise RuntimeError('write to 0x{:02x} not handled'.format(offset))

        self.update_status()

    def tick(self):
        quantum = self._counter.tick()
        self.update_status()
        self.trace('DUART', info=f'tick isr {self._isr:#x} imr {self._imr:#x}')
        return quantum

    def reset(self):
        self._a.reset()
        self._b.reset()
        self._isr = 0
        self._imr = 0
        self._ivr = 0xf
        self._count = 0
        self._countReload = 0xffff

    def get_interrupt(self):
        self.update_status()
        if self._isr & self._imr:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            if self._isr & self._imr:
                return self._ivr
        return M68K_IRQ_SPURIOUS

    def update_status(self):
        self._isr &= ~0x3b
        if self._counter.is_interrupting:
            self._isr |= 0x08
        self._isr |= self._a.get_interrupts()
        self._isr |= self._b.get_interrupts() << 4
