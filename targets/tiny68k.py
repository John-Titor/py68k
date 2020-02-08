from emulator import Emulator
from devices.CompactFlash import CompactFlash
from devices.MC68681 import MC68681
from musashi import m68k


def add_arguments(parser):
    parser.add_argument('--eeprom',
                        type=str,
                        help='EEPROM image')
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68000',
                   frequency=8 * 1000 * 1000)
    emu.add_memory(base=0, size=(16 * 1024 - 32) * 1024)
    emu.add_device(args,
                   MC68681,
                   address=0xfff001,
                   interrupt=m68k.IRQ_2,
                   console_port='A',
                   register_arrangement='16-bit')
    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000,
                   register_arrangement='16-bit')

    if args.eeprom is not None:
        rom_image = open(args.eeprom, 'rb').read(32 * 1024 + 1)
        if (len(rom_image) > (32 * 1024)):
            raise RuntimeError(f'EEPROM image {args.eeprom} must be <= 32k')
        print(f'loaded {len(rom_image)} bytes of EEPROM')
        m68k.mem_write_bulk(0, rom_image)

    return emu
