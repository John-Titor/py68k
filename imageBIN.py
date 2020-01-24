#
# Binary image loader
#
import os

from musashi.m68k import (
    mem_write_bulk,
)


class image(object):
    """
    Load a binary image
    """

    def __init__(self, emu, image_filename, max_size=-1):
        """
        Set up to read the image
        """

        self._emu = emu
        self._text_base = 0

        bytes = open(image_filename, "rb").read(max_size)
        self._text_end = self._text_base + len(bytes)

        mem_write_bulk(self._text_base, bytes)

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
