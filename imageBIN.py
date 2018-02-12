#
# Binary image loader
#
import os

from musashi.m68k import (
    mem_ram_write_block,
    mem_ram_read
)


class image(object):
    """
    Load a binary image
    """

    def __init__(self, emu, image_filename):
        """
        Set up to read the image
        """

        self._emu = emu
        self._text_base = 0

        bytes = open(image_filename, "rb").read()
        self._text_end = len(bytes)

        mem_ram_write_block(self._text_base, self._text_end, bytes)

        # check that the reset vector is sensible
        resvector = mem_ram_read(0x04, 2)

        if resvector >= self._text_end:
            raise RuntimeError(
                "binary image reset vector points outside image")

    def lineinfo(self, addr):
        return '0x{:08x}'.format(addr)

    def symname(self, addr):
        return '0x{:08x}'.format(addr)

    def symrange(self, name):
        raise RuntimeError('no symbols')

    def check_text(self, addr):
        if addr < self._text_base or addr >= self._text_end:
            return False
        return True
