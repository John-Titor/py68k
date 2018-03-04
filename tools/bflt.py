#!/usr/bin/env python
#
# uCLinux 'bFLT' executable format reader
#
# Note that this is a minimal implementation intended to serve the needs of
# the bflt2cpm converter only.
#

import struct
import sys
import os


class BFLTFile(object):
    """
    A bFLT executable generated by elf2flt (or similar).
    """

    MAGIC = (0x62, 0x46, 0x4c, 0x54)
    FILE_VERSION = 4

    FLAG_RAM = 0x0001
    FLAG_GOTPIC = 0x0002
    FLAG_GZIP = 0x0004
    FLAG_GZDATA = 0x0008

    RELOC_TEXT = 0
    RELOC_DATA = 1
    RELOC_BSS = 2
    RELOC_GOT_END = 3

    def __init__(self, withFile):
        fileBytes = bytearray(withFile.read())

        # check file magic number
        magic = struct.unpack('!4B', fileBytes[0:4])
        if magic != self.MAGIC:
            raise RuntimeError('not a bFLT file')

        # parse the header
        fmt = '!4xLLLLLLLL6x'
        headerSize = struct.calcsize(fmt)
        fields = struct.unpack(fmt, fileBytes[0:headerSize])
        (rev, entry, data_start, data_end, bss_end,
         stack_size, reloc_start, reloc_count, flags) = fields

        # check the revision
        if rev != self.FILE_VERSION:
            raise RuntimeError(
                'bFLT version {} not supported, require 4'.format(rev))

        # check for incompatible flags
        if flags & (self.FLAG_GZIP | self.FLAG_GZDATA):
            raise RuntimeError('gzip compression not supported')
        if not (flags & self.FLAG_RAM):
            raise RuntimeError(
                'XIP executable not supported, use -r option to elf2flt')

        self.text = fileBytes[entry:data_start]
        self.textSize = len(self.text)

        self.data = fileBytes[data_start:data_end]
        self.dataSize = len(self.data)

        self.bssSize = bss_end - data_end

        self.flags = flags

        # parse relocations
        self.relocs = dict()
        relocBytes = fileBytes[reloc_start:reloc_start + reloc_count * 4]
        relocEntries = struct.unpack('>{}L'.format(reloc_count), relocBytes)

        for relocAddress in relocEntries:
            relocType = __inferRelocType(relocAddress)
            self.relocs[relocAddress] = relocType

        # add GOT relocations
        if flags & self.FLAG_GOTPIC:
            for gotAddress in range(self.textSize, self.dataSize / 4, 4):
                relocType = __inferRelocType(gotAddress)
                if relocType == self.RELOC_GOT_END:
                    break
                self.relocs[gotAddress] = relocType

    def __inferRelocType(self, address):
        # read the address the relocation points at...
        if address < self.textSize:
            (targetAddress) = struct.decode(
                '>L', self.text[address:address + 4])
        elif address < (self.textSize + self.dataSize):
            location = address - self.textSize
            (targetAddress) = struct.decode(
                '>L', self.data[location:location + 4])
        else:
            raise RuntimeError('relocation points outside TEXT+DATA')

        if targetAddress < self.textSize:
            return self.RELOC_TEXT
        elif targetAddress < (self.textSize + self.dataSize):
            return self.RELOC_DATA
        elif targetAddress < (self.textSize + self.dataSize + self.bssSize):
            return self.RELOC_BSS
        elif targetAddress == 0xffffffff:
            return self.RELOC_GOT_END
        else:
            raise RuntimeError(
                'relocation target address points outside TEXT+DATA+BSS')
