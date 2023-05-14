from collections import deque
import sys

from device import Device
from musashi import m68k

class NE555Ticker(Device):
    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='NE555Ticker',
                         required_options=['interrupt'],
                         **options)

        # no registers,
        # self.size = 0x1
        # core clock @ 24MHz, 100Hz tick rate
        self._tick_cycles = int(self.emu.cycle_rate / 100)
        self.reset()
        self._start()
        self.trace(info='init done')

    def reset(self):
        self._vr = 0
        self._stop()
        self._tick_fired = False

    def access(self, operation, offset, size, value):
        if value  > 0:
            self._start()
        else:
            self._stop()

    def _stop(self):
        self.trace(info=f'ticker stopped')
        self.callback_cancel('tick')
        self._ticker_on = False

    def _start(self):
        if not self._ticker_on:
            self.trace(info=f'ticker start every {self._tick_cycles}')
            self.callback_every(self._tick_cycles, 'tick', self._tick)
            self._ticker_on = True

    def _tick(self):
        if self._ticker_on:
            self._tick_fired = True
            self.assert_ipl()

    def get_vector(self, interrupt):
        if self._tick_fired:
            self._tick_fired = False
            if self._vr > 0:
                return self._vr
            return m68k.IRQ_AUTOVECTOR
        return m68k.IRQ_SPURIOUS
