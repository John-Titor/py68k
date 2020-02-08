import emulator
import device
import devices.p90ce201


def add_arguments(parser):
    """add commandline argument definitions to the parser"""
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    devices.p90ce201.add_arguments(parser,
                                   default_console_port='0')
    CompactFlash.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""

    emu = emulator.Emulator(args,
                            frequency=24 * 1000 * 1000
                            cpu="68070")
    emu.add_memory(base=0, size=512 * 1024, writable=False, from_file=args.rom)
    emu.add_memory(base=0x1000000, size=512 * 1024)
    devices.p90ce201.add_devices(args, emu)
    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000)

    return emu
