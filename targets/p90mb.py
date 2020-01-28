import emulator
import device
import devices.p90ce201


def add_arguments(parser):
    """add commandline argument definitions to the parser"""
    devices.p90ce201.add_arguments(parser)


def configure(args):
    """create and configure an emulator"""
    mmap = {
        "ROM": (0, 512 * 1024),
        "RAM": (0x1000000, 512 * 1024)
    }
    emu = emulator.Emulator(args,
                            memory_map=mmap,
                            cpu="68070")

    emu.add_device(args, device.RootDevice, 0xff8000)
    devices.p90ce201.add_devices(args)

    emu.add_device(args,
                   MC68681,
                   address=0xfff000,
                   interrupt=emulator.M68K_IRQ_2)

    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000)

    return emu
