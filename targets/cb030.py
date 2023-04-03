from emulator import Emulator
from device import Device
from devices.compactflash import CompactFlash
from devices.mc68681 import MC68681
from musashi import m68k


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    parser.add_argument('--dram-size',
                        type=int,
                        default=16,
                        help='DRAM size; boards may have 16, 64 or 128M')
    parser.add_argument('--cf-width',
                        type=int,
                        default=8,
                        help='CompactFlash interface width, 8 or 16')
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser)


class CB030Remap(Device):
    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='CB030Remap',
                         required_options=['address'],
                         **options)

        # no registers, just a 4k aperture
        self.size = 0x1000
        self._did_remap = False
        self._dram_size = args.dram_size

    def access(self, operation, offset, size, value):
        if not self._did_remap:
            # remove the low alias of the EEPROM
            self.emu.remove_memory(base=0)

            # and add the previously-masked DRAM
            self.emu.add_memory(base=0x0000000, size=self._dram_size * 1024 * 1024)

        return 0


class CB030Ticker(Device):
    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='CB030Ticker',
                         required_options=['address'],
                         **options)

        # no registers, just a 4k aperture
        self.size = 0x1000
        # core clock @ 24MHz, 100Hz tick rate
        self._tick_cycles = int(self.emu.cycle_rate / 100)
        self.reset()

    def reset(self):
        self._stop()
        self._tick_fired = False

    def access(self, operation, offset, size, value):
        if offset < 0x800:
            self._stop()
        else:
            self._start()

    def _stop(self):
        self.callback_cancel('tick')
        self._ticker_on = False

    def _start(self):
        if not self._ticker_on:
            self.callback_every(self._tick_cycles, 'tick', self._tick)
            self._ticker_on = True

    def _tick(self):
        if self._ticker_on:
            self._tick_fired = True
            self.assert_ipl()

    def get_vector(self):
        if self._tick_fired:
            self._tick_fired = False
            return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68030',
                   frequency=24 * 1000 * 1000)
    # initially only the EEPROM exists; aliased at 0 all the way up to 0xfe000000
    # we only map the low and high aliases, as the intermediates aren't interesting
    emu.add_memory(base=0, size=512 * 1024, writable=False, from_file=args.rom)
    emu.add_memory(base=0xfe000000, size=512 * 1024, writable=False, from_file=args.rom)

    emu.add_device(args,
                   MC68681,
                   address=0xfffff000,
                   interrupt=m68k.IRQ_2,
                   register_arrangement='16-bit-doubled')
    emu.add_device(args,
                   CompactFlash,
                   address=0xffffe000,
                   register_arrangement='8-bit' if args.cf_width == 8 else '16-bit')
    emu.add_device(args,
                   CB030Remap,
                   address=0xffff8000)
    emu.add_device(args,
                   CB030Ticker,
                   address=0xffff9000,
                   interrupt=m68k.IRQ_6)
    return emu
