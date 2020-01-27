from pathlib import Path

import emulator
import device
from devices.CompactFlash import CompactFlash
from devices.MC68681 import MC68681
from musashi.m68k import mem_write_bulk

rom_image = None


def add_arguments(parser):
    parser.add_argument('--rom',
                        type=str,
                        help='ROM image to load at reset')
    CompactFlash.add_arguments(parser)
    MC68681.add_arguments(parser)


def reset_hook(emu):
    """called at reset time, emulates the ROM (re) load to RAM"""
    mem_write_bulk(0, rom_image)


def configure(args):
    """create and configure an emulator"""

    if args.rom is not None:
        p = Path(args.rom)
        if p.suffix.lower() == "bin":
            rom_image = imageBIN.image(33 * 1024)
            if (len(rom_image) != (32 * 1024)):
                raise RuntimeError(f"ROM image {args.rom} must be 32k")

    emu = emulator.Emulator(args,
                            cpu="68000",
                            frequency=8 * 1000 * 1000)
    emu.add_reset_hook(reset_hook)
    emu.add_memory(base=0, size=(16 * 1024 - 32) * 1024)
    emu.add_device(args, device.root_device)
    emu.add_device(args,
                   MC68681,
                   address=0xfff000,
                   interrupt=emulator.M68K_IRQ_2)
    emu.add_device(args,
                   CompactFlash,
                   address=0xffe000)
    return emu
