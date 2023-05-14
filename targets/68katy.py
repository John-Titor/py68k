from emulator import Emulator
#from devices.compactflash import CompactFlash
from devices.ne555 import NE555Ticker
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
ram_size = 1024 * 512 # 0x0FFFFF - 0x080000 + 1 # 512 * 1024

io_base  = 0x078000 


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image')
    #CompactFlash.add_arguments(parser)

    NE555Ticker.add_arguments(parser)
    FT245RL.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""

    emu = Emulator(args,
                   cpu='68000',
                   frequency=8 * 1000 * 1000)

    emu.add_memory(base=rom_base, size=rom_size, writable=False, from_file=args.rom)
    emu.add_memory(base=ram_base, size=ram_size)
    emu.add_device(args,
                   NE555Ticker,
                   interrupt=m68k.IRQ_5)
    emu.add_device(args,
                   FT245RL,
                   address=io_base,
                   interrupt=m68k.IRQ_2)
   
    return emu
