import sys
from device import device
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

    def __init__(self, parent):
        self.reset()
        self._parent = parent

    @classmethod
    def add_arguments(cls, parser):
        """add argument definitions for args passed to __init__"""
        pass

    def reset(self):
        self._mr1 = 0
        self._mr2 = 0
        self._mrAlt = False
        self._sr = 0
        self._rxfifo = deque()
        self._rxEnable = False
        self._txEnable = False

    def read(self, addr):
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

        # default read result
        else:
            value = 0xff

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

        elif addr == Channel.REG_TB:
            device.root_device.console_output(value)

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

    def handle_console_input(self, input):
        self._rxfifo.append(input)
        self.update_status()
        self._parent.update_status()


class Counter():

    MODE_MASK = 0x70
    MODE_CTR_XTAL16 = 0x30
    MODE_TMR_XTAL = 0x60
    MODE_TMR_XTAL16 = 0x70

    def __init__(self, parent):
        self._parent = parent
        self._last_tick_cyclecount = 0
        self._counter_reload = 0x0100
        self._interrupting = False

        self.set_mode(Counter.MODE_TMR_XTAL16)
        self._counter_epoch = self._parent.current_cycle + self._period

    def set_mode(self, mode):
        mode &= Counter.MODE_MASK
        if mode == Counter.MODE_CTR_XTAL16:
            self._prescale = 16
        elif mode == Counter.MODE_TMR_XTAL:
            self._prescale = 1
        elif mode == Counter.MODE_TMR_XTAL16:
            self._prescale = 16
        else:
            raise RuntimeError(
                'timer mode 0x{:02x} not supported'.format(mode))

        self._mode = mode
        if self._mode_is_timer:
            self._running = True
            self._timer_toggle = 0

    def set_reload_low(self, value):
        self._counter_reload = (self._counter_reload & 0xff00) | value

    def set_reload_high(self, value):
        self._counter_reload = (self._counter_reload & 0x00ff) | (value << 8)

    def start(self):
        self._counter_epoch = self._parent.current_cycle + \
            self._counter_reload * self._clock_scale_factor
        self._running = True

        if self._mode_is_timer:
            self._timer_toggle = 0

    def stop(self):
        self._interrupting = False

        if self._mode_is_counter:
            self._running = False

    def get_counter(self):
        # handle possibly passing the counter epoch; guarantees the epoch is in the future
        self.tick()

        cycles_remaining = self._counter_epoch - self.current_cycle
        return int(round(cycles_remaining / self._clock_scale_factor))

    @property
    def is_interrupting(self):
        return self._interrupting

    def tick(self):
        """
        Adjust the state of the counter up to the current time
        """

        # do nothing if we're not running
        if not self._running:
            return 0

        current_cycle = self._parent.current_cycle
        if current_cycle >= self._counter_epoch:
            if self._mode_is_counter:
                self._interrupting = True
            else:
                if self._timer_toggle == 0:
                    self._timer_toggle = 1
                else:
                    self._timer_toggle = 0
                    self._interrupting = 1

            periods_since_epoch = (
                current_cycle - self._counter_epoch) / self._period
            self._parent.trace('update', 'late {} period {} since epoch {}'.format(current_cycle - self._counter_epoch,
                                                                                   self._period,
                                                                                   periods_since_epoch))
            self._counter_epoch = self._counter_epoch + \
                (periods_since_epoch + 1) * self._period

        self._parent.trace('tick', 'at {} deadline {} limit {}'.format(
            current_cycle, self._counter_epoch, self._counter_epoch - current_cycle))

        # limit the next quantum to the deadline
        return self._counter_epoch - current_cycle

    @property
    def _period(self):
        if self._mode_is_counter:
            # counter wraps to 0xffff
            value = 0x10000 * self._clock_scale_factor
        else:
            # timer wraps to reload value
            value = self._counter_reload * self._clock_scale_factor
        return int(round(value))

    @property
    def _mode_is_counter(self):
        return self._mode < 0x40

    @property
    def _mode_is_timer(self):
        return not self._mode_is_counter

    @property
    def _clock_scale_factor(self):
        return (self._parent.cycle_rate / 3.6) * self._prescale


class MC68681(device):
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

        self._a = Channel(self)
        self._b = Channel(self)
        self._counter = Counter(self)
        self.reset()
        self.trace('init done')

        device.root_device.register_console_input_driver(self._a)

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
        if self._isr & self._imr:
            return self._interrupt
        return 0

    def get_vector(self, interrupt):
        if self._isr & self._imr:
            return self._ivr
        return M68K_IRQ_SPURIOUS

    def update_status(self):
        self._isr &= ~0x3b
        if self._counter.is_interrupting:
            self._isr |= 0x08
        self._isr |= self._a.get_interrupts()
        self._isr |= self._b.get_interrupts() << 4
