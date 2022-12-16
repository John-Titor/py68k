from emulator import Emulator
from device import Device
#from devices.compactflash import CompactFlash
from devices.ft245rl import FT245RL
from musashi import m68k


# @see https://www.bigmessowires.com/68-katy/

# /> cat /proc/interrupts
# auto  2:         21 L FT245 console
# auto  5:       6017 L timer
# auto  7:          0 L timer-and-serial
# 68000 autovector interrupts

rom_base = 0
rom_size = 0x077FFF + 1 # 512 * 1024 but not all the flash is decoded

ram_base = 0x080000
ram_size = 0x0FFFFF - 0x080000 + 1 # 512 * 1024

io_base  = 0x078000 


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    #CompactFlash.add_arguments(parser)
    FT245RL.add_arguments(parser)


class Katy68Ticker(Device):
    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='Katy68Ticker',
                         required_options=['interrupt'],
                         **options)

        # no registers, 
        # self.size = 0x0
        # core clock @ 24MHz, 100Hz tick rate
        self._tick_cycles = int(self.emu.cycle_rate / 100)
        self.reset()
        self._start()
        self.trace(info='init done')

    def reset(self):
        self._vr = 0
        self._stop()
        self._tick_fired = False

        self._start()

    def _stop(self):
        self.trace(info=f'ticker stoped')
        self.callback_cancel('tick')
        self._ticker_on = False

    def _start(self):
        if not self._ticker_on:
            self.trace(info=f'ticker started every {self._tick_cycles}')
            self.callback_every(self._tick_cycles, 'tick', self._tick)
            self._ticker_on = True

    def _tick(self):
        if self._ticker_on:
            self._tick_fired = True
            self.assert_ipl()

    def get_vector(self):
        if self._tick_fired:
            self._tick_fired = False
            if self._vr > 0:
                return self._vr
            return mk68.IRQ_AUTOVECTOR
        return m68k.IRQ_SPURIOUS


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68000',
                   frequency=8 * 1000 * 1000)

    emu.add_memory(base=rom_base, size=rom_size, writable=False, from_file=args.rom)
    emu.add_memory(base=ram_base, size=ram_size)
    emu.add_device(args,
                   Katy68Ticker,
                   interrupt=m68k.IRQ_5)
    emu.add_device(args,
                   FT245RL,
                   address=io_base,
                   interrupt=m68k.IRQ_2)
   
    return emu
