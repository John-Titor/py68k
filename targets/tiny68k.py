from emulator import Emulator, M68K_IRQ_2
from devices.CompactFlash import CompactFlash
from devices.MC68681 import MC68681
from musashi.m68k import mem_write_bulk


def add_arguments(parser):
    parser.add_argument('--eeprom',
                        type=str,
                        help='ROM image to load at reset')
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser,
                          default_console_port='A')


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu="68000",
                   frequency=8 * 1000 * 1000)
    emu.add_memory(base=0, size=(16 * 1024 - 32) * 1024)
    emu.add_device(args,
                   MC68681,
                   address=0xfff000,
                   interrupt=M68K_IRQ_2)
    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000)

    if args.eeprom is not None:
        rom_image = open(args.eeprom, "rb").read(32 * 1024 + 1)
        if (len(rom_image) > (32 * 1024)):
            raise RuntimeError(f"ROM image {args.eeprom} must be <= 32k")
        print(f'loaded {len(rom_image)} bytes of EEPROM')
        mem_write_bulk(0, rom_image)

    return emu
