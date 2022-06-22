from emulator import Emulator
from devices.mc68681 import MC68681
from musashi import m68k

ram_base = 0
ram_size = 1024 * 1024
rom_base = 0xe00000
rom_size = 512 * 1024


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    MC68681.add_arguments(parser)


def roscov2_reset_callback():
    m68k.set_reg(m68k.REG_SP, m68k.mem_read_memory(rom_base, MEM_SIZE_32));
    m68k.set_reg(m68k.REG_PC, m68k.mem_read_memory(rom_base + 4, MEM_SIZE_32));


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68010',
                   frequency=10 * 1000 * 1000)
    emu.add_memory(base=ram_base, size=ram_size)
    emu.add_memory(base=rom_base, size=rom_size, writable=False, from_file=args.rom)
    emu.add_device(args,
                   MC68681,
                   address=0xf00001,
                   interrupt=m68k.IRQ_4,
                   console_port='A',
                   register_arrangement='16-bit')

    # emulate first-4-cycles ROM jam - should USE_CYCLES(4) but no API for this
    emu.add_reset_hook(roscov2_reset_callback)

    return emu
