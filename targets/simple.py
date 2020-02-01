from emulator import Emulator, M68K_IRQ_2, M68K_IRQ_6
from devices.simple import UART, Timer


def add_arguments(parser):
    parser.add_argument('--cpu_type',
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
    UART.add_arguments(parser)
    Timer.add_arguments(parser)


def configure(args):
    if args.cpu_type == '68000':
        if args.mem_size > 15:
            raise RuntimeError('max memory for 68000 emulation is 15MB')
        iobase = 0xff0000
    else:
        iobase = 0xffff0000

    emu = Emulator(args,
                   cpu=args.cpu_type,
                   frequency=args.cpu_frequency * 1000 * 1000)
    emu.add_memory(base=0, size=args.mem_size * 1024 * 1024)
    emu.add_device(args,
                   UART,
                   address=iobase,
                   interrupt=M68K_IRQ_2)
    emu.add_device(args,
                   Timer,
                   address=iobase + 0x1000,
                   interrupt=M68K_IRQ_6)

    return emu
