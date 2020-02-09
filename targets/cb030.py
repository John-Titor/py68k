from emulator import Emulator
from devices.CompactFlash import CompactFlash
from devices.MC68681 import MC68681
from musashi import m68k


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68030',
                   frequency=24 * 1000 * 1000)
    emu.add_memory(base=0, size=512 * 1024, writable=False, from_file=args.rom)
    emu.add_memory(base=0x4000000, size=64 * 1024 * 1024)
    emu.add_device(args,
                   MC68681,
                   address=0xfffff000,
                   interrupt=m68k.IRQ_2,
                   register_arrangement='16-bit')
    emu.add_device(args,
                   CompactFlash,
                   address=0xffffe000,
                   register_arrangement='8-bit')

    return emu
