from emulator import Emulator
from musashi import m68k
from devices.simple import UART, Timer


def add_arguments(parser):
    parser.add_argument('--cpu-type',
                        type=str,
                        choices=['68000',
                                 '68010',
                                 '68EC020',
                                 '68020',
                                 '68EC030',
                                 '68030',
                                 '68EC040',
                                 '68LC040',
                                 '68040',
                                 'SCC68070'],
                        metavar='CPU-TYPE',
                        default='68000',
                        help='CPU to emulate')
    parser.add_argument('--cpu-frequency',
                        type=int,
                        choices=range(1, 100),
                        metavar='FREQUENCY-MHZ',
                        default=8,
                        help='CPU frequency to emulate')
    parser.add_argument('--mem-size',
                        type=int,
                        choices=range(1, 255),
                        default=15,
                        metavar='SIZE-MB',
                        help='memory size')
    Timer.add_arguments(parser)
    UART.add_arguments(parser)


def configure(args):
    iobase = 0xff0000

    emu = Emulator(args,
                   cpu=args.cpu_type,
                   frequency=args.cpu_frequency * 1000 * 1000)
    emu.add_memory(base=0, size=args.mem_size * 1024 * 1024)
    emu.add_device(args,
                   UART,
                   address=iobase,
                   interrupt=m68k.IRQ_2)
    emu.add_device(args,
                   Timer,
                   address=iobase + 0x1000,
                   interrupt=m68k.IRQ_6)

    return emu
