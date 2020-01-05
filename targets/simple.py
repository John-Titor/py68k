import emulator
import device


def configure(args):
    emu = emulator.Emulator(args, memory_size=128)

    # add some devices
    emu.add_device(args, device.root_device, 0xff0000)
    emu.add_device(args, device.uart, 0xff0000, emulator.M68K_IRQ_2)
    emu.add_device(args, device.timer, 0xff1000, emulator.M68K_IRQ_6)

    return emu
