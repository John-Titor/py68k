from emulator import Emulator
from device import Device
from devices.compactflash import CompactFlash
from devices import p90ce201
from musashi import m68k

p90_flipped = False


def add_arguments(parser):
    """add commandline argument definitions to the parser"""
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    p90ce201.add_arguments(parser)
    CompactFlash.add_arguments(parser)


def rom_flip(app, apcon):
    global p90_flipped
    a23 = bool(0x80 & apcon & app)
    if a23 != p90_flipped:
        # move memory at 0 to temporary location
        m68k.mem_move_memory(src=0,
                             dst=0x2000000)
        # move memory at 0x1000000 to 0
        m68k.mem_move_memory(src=0x1000000,
                             dst=0x0000000)
        # move memory from temporary location to 0x1000000
        m68k.mem_move_memory(src=0x2000000,
                             dst=0x1000000)
        p90_flipped = a23


def configure(args):
    """create and configure an emulator"""
    fosc = 24 * 1000 * 1000
    emu = Emulator(args,
                   cpu='SCC68070',
                   frequency=fosc / 2)
    emu.add_memory(base=0,
                   size=512 * 1024,
                   writable=False,
                   from_file=args.rom)
    emu.add_memory(base=0x1000000,
                   size=512 * 1024)
    p90ce201.add_devices(args,
                         emu,
                         fosc)
    emu.add_device(args,
                   CompactFlash,
                   address=0x1200000,
                   register_arrangement='8-bit')

    aux = Device.find_device('P90AUX')
    aux.set_callback(rom_flip)

    return emu
