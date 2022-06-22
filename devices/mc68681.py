import sys
from device import Device, Register
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

    def __init__(self, parent, port, is_console=False):
        self._parent = parent
        self._port = port
        self._is_console = is_console
        if self._is_console:
            self._parent.register_console_input_handler(self._handle_console_input)
        self.reset()

    def reset(self):
        self._mr1 = 0
        self._mr2 = 0
        self._mrAlt = False
        self._rxfifo = deque()
        self._rxEnable = False
        self._txEnable = False
        self._tsrEmpty = True
        self._thrEmpty = True
        self._update_isr()

    def read_mr(self):
        if self._mrAlt:
            return self._mr2
        else:
            self._mrAlt = True
            return self._mr1

    def read_sr(self):
        value = 0
        if self._tsrEmpty:
            value |= self.STATUS_TRANSMITTER_EMPTY
        if self._thrEmpty:
            value |= self.STATUS_TRANSMITTER_READY
        rxcount = len(self._rxfifo)
        if rxcount > 0:
            value |= self.STATUS_RECEIVER_READY
            if (rxcount > 2):
                value |= self.STATUS_FIFO_FULL
        return value

    def read_rb(self):
        value = 0xff
        if len(self._rxfifo) > 0:
            value = self._rxfifo.popleft()
            self._update_isr()
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
        if value & self.CTRL_RXDIS:
            self._rxEnable = False
        elif value & self.CTRL_RXEN:
            self._rxEnable = True
        if value & self.CTRL_TXDIS:
            self._txEnable = False
        elif value & self.CTRL_TXEN:
            self._txEnable = True

        cmd = value & self.CTRL_CMD_MASK
        if cmd == self.CTRL_MRRST:
            self._mrAlt = False
        elif cmd == self.CTRL_RXRST:
            self._rxEnable = False
            self._rxfifo.clear()
        elif cmd == self.CTRL_TXRST:
            self._txEnable = False
            # self._txfifo
        self._update_isr()

    def write_tb(self, value):
        if self._is_console:
            self._parent.console_handle_output(chr(value).encode('latin-1'))
        if self._tsrEmpty:
            # send straight to shift register
            self._tx_start()
        else:
            # buffer in holding register
            self._thrEmpty = False

    def _tx_start(self):
        # start "transmitting" a byte
        self._tsrEmpty = False
        # 38400bps = ~200µs / byte = ~2000 8MHz CPU cycles
        self._parent.callback_after(2000, f'tsr{self._port}', self._tx_done)

    def _tx_done(self):
        # byte "transmission" completed
        self._tsrEmpty = True
        # next byte in holding register, start "transmitting" it
        if not self._thrEmpty:
            self._thrEmpty = True
            self._tx_start()

    def _update_isr(self):
        isr = 0
        if self._txEnable:
            isr |= self.INT_TXRDY
        if self._rxEnable:
            if len(self._rxfifo) > (2 if self._mr1 & self.MR1_FFULL_EN else 0):
                isr |= self.INT_RXRDY_FFULL
        self._parent.update_channel_isr(self._port, isr)

    def _handle_console_input(self, input):
        if self._rxEnable:
            for c in input:
                self._rxfifo.append(c)
            self._update_isr()


class MC68681(Device):
    """
    Emulation of the MC68681 DUART / timer device.

    Notes:
        Timer mode behaviour when the reload value is changed is not correct;
        the new reload value should only be taken when the timer rolls over.

    """

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

    def __init__(self, args, **options):
        super(MC68681, self).__init__(args=args,
                                      name='MC68681',
                                      required_options=['address', 'interrupt', 'register_arrangement'],
                                      **options)

        self._isr = 0
        self._imr = 0

        console_port = options['console_port'] if 'console_port' in options else 'A'
        self._a = Channel(self, 'A', console_port == 'A')
        self._b = Channel(self, 'B', console_port == 'B')

        if options['register_arrangement'] == '16-bit':
            self.add_registers([
                ('MRA',         0x00, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_mr),
                ('SRA',         0x02, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_sr),
                ('RBA',         0x06, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_rb),
                ('IPCR',        0x08, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ipcr),
                ('ISR',         0x0a, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_isr),
                ('CUR',         0x0c, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cur),
                ('CLR',         0x0e, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_clr),
                ('MRB',         0x10, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_mr),
                ('SRB',         0x12, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_sr),
                ('RBB',         0x16, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_rb),
                ('IVR',         0x18, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ivr),
                ('IPR',         0x1a, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ipr),
                ('STARTCC',     0x1c, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_startcc),
                ('STOPCC',      0x1e, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_stopcc),

                ('MRA',         0x00, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_mr),
                ('CSRA',        0x02, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_csr),
                ('CRA',         0x04, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_cr),
                ('TBA',         0x06, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_tb),
                ('ACR',         0x08, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_acr),
                ('IMR',         0x0a, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_imr),
                ('CTUR',        0x0c, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ctur),
                ('CTLR',        0x0e, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ctlr),
                ('MRB',         0x10, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_mr),
                ('CSRB',        0x12, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_csr),
                ('CRB',         0x14, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_cr),
                ('TBB',         0x16, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_tb),
                ('IVR',         0x18, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ivr),
#                ('OPCR',        0x1a, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_opcr),
#                ('OPSET',       0x1c, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_opset),
#                ('OPRST',       0x1e, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_oprst),
            ])
        elif options['register_arrangement'] == '8-bit':
            self.add_registers([
                ('MRA',         0x00, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_mr),
                ('SRA',         0x01, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_sr),
                ('RBA',         0x03, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._a.read_rb),
                ('IPCR',        0x04, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ipcr),
                ('ISR',         0x05, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_isr),
                ('CUR',         0x06, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cur),
                ('CLR',         0x07, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_clr),
                ('MRB',         0x08, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_mr),
                ('SRB',         0x09, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_sr),
                ('RBB',         0x0b, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._b.read_rb),
                ('IVR',         0x0c, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ivr),
                ('IPR',         0x0d, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_ipr),
                ('STARTCC',     0x0e, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_startcc),
                ('STOPCC',      0x0f, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_stopcc),

                ('MRA',         0x00, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_mr),
                ('CSRA',        0x01, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_csr),
                ('CRA',         0x02, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_cr),
                ('TBA',         0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._a.write_tb),
                ('ACR',         0x04, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_acr),
                ('IMR',         0x05, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_imr),
                ('CTUR',        0x06, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ctur),
                ('CTLR',        0x07, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ctlr),
                ('MRB',         0x08, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_mr),
                ('CSRB',        0x09, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_csr),
                ('CRB',         0x0a, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_cr),
                ('TBB',         0x0b, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._b.write_tb),
                ('IVR',         0x0c, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_ivr),
            ])
        else:
            raise RuntimeError(f'register_arrangement {options["register_arrangement"]} not recognized')

        self.reset()
        self.trace(info='init done')

    def _read_ipcr(self):
        return 0x03  # CTSA/CTSB are always asserted

    def _read_isr(self):
        return self._isr

    def _read_ivr(self):
        return self._ivr

    def _read_ipr(self):
        return 0x03  # CTSA/CTSB are always asserted

    def _read_cur(self):
        return self._count >> 8

    def _read_clr(self):
        return self._count & 0xff

    def _read_startcc(self):
        self._count = 0xffff
        if self._mode_is_counter:
            self._counter_deadline = self.current_cycle + self._reload * self._scaler
            self.callback_at(self._counter_deadline, 'counter/timer', self._callback)
        else:
            self._timer_epoch = self.current_cycle
            deadline = int(self._timer_epoch + self._timer_period)
            self.trace(info=f'timer startcc, epoch {self._timer_epoch} deadline {deadline}')
            self.callback_at(deadline, 'counter/timer', self._callback)

        return 0xff

    def _read_stopcc(self):
        self._isr &= ~self.IMR_COUNTER
        self._update_ipl()
        if self._mode_is_counter:
            self.callback_cancel('counter/timer')
            overrun = int((self.current_time - self._counter_deadline) / self._scaler)
            if overrun < 0:
                self._count = -overrun
            else:
                self._count = int(0x10000 - overrun)
        else:
            # round_up(self._current_cycle, self._timer_period)
            elapsed = self.current_cycle - self._timer_epoch
            deadline = int((int(elapsed / self._timer_period) + 1) * self._timer_period)
            self.trace(info=f'timer stopcc, epoch {self._timer_epoch} deadline {deadline}')
            self.callback_at(deadline, 'counter/timer', self._callback)

        return 0xff

    def _write_imr(self, value):
        self._imr = value
        self._update_ipl()

    def _write_ivr(self, value):
        self._ivr = value

    def _write_acr(self, value):
        mode = value & self.MODE_MASK
        cycle_ratio = self.cycle_rate / 3686400.0

        if (mode == self.MODE_CTR_TXCA) or (mode == self.MODE_CTR_TXCB):
            self._scaler = cycle_ratio * 96     # assume 38400bps
        elif mode == self.MODE_CTR_XTAL16:
            self._scaler = cycle_ratio * 16
        elif mode == self.MODE_TMR_XTAL:
            self._scaler = cycle_ratio * 1
        elif mode == self.MODE_TMR_XTAL16:
            self._scaler = cycle_ratio * 16
        else:
            raise RuntimeError(f'counter/timer mode {mode:#02x} not supported')

        self._mode = mode
        self.callback_cancel('counter/timer')

    def _write_ctlr(self, value):
        self._reload = (self._reload & 0xff00) | value

    def _write_ctur(self, value):
        self._reload = (self._reload & 0x00ff) | (value << 8)

    def update_channel_isr(self, port, isr):
        if port == 'A':
            self._isr &= ~0x03
            self._isr |= isr
        elif port == 'B':
            self._isr &= -0x30
            self._isr |= (isr << 4)
        self._update_ipl()

    def _callback(self):
        self._isr |= self.IMR_COUNTER
        self._update_ipl()

    def _update_ipl(self):
        if (self._isr & self._imr) != 0:
            self.assert_ipl()
        else:
            self.deassert_ipl()

    def reset(self):
        self._a.reset()
        self._b.reset()
        self._isr = 0
        self._imr = 0
        self._ivr = 0xf
        self._reload = 0x0001
        self._write_acr(self.MODE_TMR_XTAL16)
        self._read_startcc()

    def get_vector(self, interrupt):
        return self._ivr if (self._imr & self._isr) != 0 else m68k.IRQ_SPURIOUS

    @property
    def _mode_is_counter(self):
        return not self._mode_is_timer

    @property
    def _mode_is_timer(self):
        return self._mode & self.MODE_TMR

    @property
    def _timer_period(self):
        return 2 * self._reload * self._scaler
