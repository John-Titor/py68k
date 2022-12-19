from collections import deque
import sys

from device import Device
from musashi import m68k


# @see https://www.bigmessowires.com/68-katy/
ADDR_SERIN         = 0x078000
ADDR_SEROUT        = 0x07A000
ADDR_SERSTATUS_RXF = 0x07C000
ADDR_SERSTATUS_TXE = 0x07D000
ADDR_DOUT          = 0x07E000

class FT245RL(Device):

    SERSTATUS_RXF = 0b11111110 #  b0 is 0 when fifo ready to read
    SERSTATUS_TXE = 0b11111110 #  b0 is 0 when fifo is empty


    def __init__(self, args, **options):
        super(FT245RL, self).__init__(args=args,
                                      name='FT245RL',
                                      required_options=['address', 'interrupt'],
                                      **options)

        self.add_registers([ 
            ('SERIN',         0x00,                              m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_serin),
            ('SERSTATUS_RXF', (ADDR_SERSTATUS_RXF - ADDR_SERIN), m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_sr_rxf),
            ('SERSTATUS_TXE', (ADDR_SERSTATUS_TXE - ADDR_SERIN), m68k.MEM_SIZE_8, m68k.MEM_READ, self._read_sr_txe),

            ('SEROUT',        (ADDR_SEROUT - ADDR_SERIN),        m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_serout),
            ('DOUT',          (ADDR_DOUT - ADDR_SERIN),          m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_dout),
        ])

        self.register_console_input_handler(self._handle_console_input)
        self.reset()
        self.trace(info='init done')

    def reset(self):
        self._rxfifo = deque()
        self._vr = 0

    def _read_sr_rxf(self):
        value = 0b11111111
        if len(self._rxfifo) > 0:
            value = FT245RL.SERSTATUS_RXF
        return value

    def _read_sr_txe(self):
        value = FT245RL.SERSTATUS_TXE
        return value


    def _read_serin(self):
        if len(self._rxfifo) > 0:
            return self._rxfifo.popleft()
            self._update_ipl()
        return 0

    def _write_serout(self, value):
        #print("OUTPUT=" + str(chr(value).encode('latin-1')))
        self.console_handle_output(chr(value).encode('latin-1'))

    def _write_dout(self, value):
        self.trace(info='LED=' + str(value))

    def get_vector(self, interrupt):
        if self._vr > 0:
            return self._vr
        #return m68k.IRQ_AUTOVECTOR
        return m68k.IRQ_SPURIOUS

    def _update_ipl(self):
        if (len(self._rxfifo) > 0):
           self.assert_ipl()
        else:
           self.deassert_ipl()

    def _handle_console_input(self, input):
        for c in input:
            self._rxfifo.append(c)
        self._update_ipl()




