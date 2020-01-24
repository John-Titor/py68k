import emulator
import device
from devices.CompactFlash import CompactFlash
from devices.MC68681 import MC68681


def add_arguments(parser):
    """add commandline argument definitions to the parser"""
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""
    emu = emulator.Emulator(args, 
                            memory_size=(16 * 1024 - 32),
                            cpu="68000")

    emu.add_device(args, device.root_device, 0xff8000)

    emu.add_device(args,
                   MC68681,
                   address=0xfff000,
                   interrupt=emulator.M68K_IRQ_2)

    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000)

    return emu
