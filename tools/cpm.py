#!/usr/bin/env python
#
# CP/M 68K executable format tools
#

import struct
import sys
import os
from hexdump import hexdump

# object file types
TYPE_CONTIG = 0x601a
TYPE_NONCONTIG = 0x601b

# header relocation-present flag
NO_RELOCS = 0xffff
WITH_RELOCS = 0x0000

# symbol type flags
SYM_TYPE_DEFINED = 0x8000
SYM_TYPE_EQUATED = 0x4000
SYM_TYPE_GLOBAL = 0x2000
SYM_TYPE_EQUATED_REG = 0x1000
SYM_TYPE_EXTERNAL_REF = 0x0800
SYM_TYPE_DATA_RELOC = 0x0400
SYM_TYPE_TEXT_RELOC = 0x0200
SYM_TYPE_BSS_RELOC = 0x0100

# relocation types
RELOC_TYPE_ABSOLUTE = 0x0000
RELOC_TYPE_DATA = 0x0001
RELOC_TYPE_TEXT = 0x0002
RELOC_TYPE_BSS = 0x0003
RELOC_TYPE_UNDEFINED = 0x0004   # not supported here
RELOC_TYPE_UPPER = 0x0005
RELOC_TYPE_PCREL = 0x0006       # not supported here
RELOC_TYPE_INSTRUCTION = 0x0007
RELOC_TYPE_MASK = 0x0007
RELOC_TYPE_INDEX_MASK = 0xfff8
RELOC_TYPE_INDEX_SHIFT = 3

# internal relocation codes
RELOC_SIZE_16 = 0x10000
RELOC_SIZE_32 = 0x20000
RELOC_SIZE_MASK = 0x30000


class CPMFile(object):
    """
    A CPM executable ('load file' or 'command file')
    """

    def __init__(self, text, textAddress, data, bssSize, relocs):
        self.text = text
        self.textAddress = textAddress

        self.data = data
        self.dataAddress = textAddress + len(text)

        self.bssSize = bssSize
        self.bssAddress = self.dataAddress + len(data)

        self.relocs = relocs

    @classmethod
    def load(cls, fo):
        """
        Parse a CP/M 68K executable and load the interesting parts
        """

        fileBytes = bytearray(fo.read())

        # get the filetype
        magic = struct.unpack('>H', fileBytes[0:2])
        if magic[0] == TYPE_CONTIG:
            fmt = '>HLLLLLLH'
        elif magic[0] == TYPE_NONCONTIG:
            raise RuntimeError('non-contiguous text/data format not supported')
        else:
            raise RuntimeError('invalid header magic 0x{:04x}'.format(magic))

        # decode the header to find things in the file
        headerSize = struct.calcsize(fmt)
        fields = struct.unpack(fmt, fileBytes[0:headerSize])

        textSize = fields[1]
        textStart = headerSize
        textEnd = textStart + textSize

        dataSize = fields[2]
        dataStart = textEnd
        dataEnd = dataStart + dataSize

        symtabSize = fields[4]
        symtabStart = dataEnd
        symtabEnd = symtabStart + symtabSize

        if fields[7] == WITH_RELOCS:
            relocStart = symtabEnd
            relocEnd = relocStart + textSize + dataSize
        else:
            relocEnd = symtabEnd

        # check filesize
        if relocEnd > len(fileBytes):
            raise RuntimeError('header / file size mismatch')

        # build out our internal representation of the file
        text = fileBytes[textStart:textEnd]
        textAddress = fields[6]
        data = fileBytes[dataStart:dataEnd]
        bssSize = fields[3]

        # ignore syms

        relocs = dict()
        if fields[7] == WITH_RELOCS:
            if textAddress > 0:
                raise RuntimeError('relocatable file but text address != 0')
            relocs = cls.decodeRelocs(fileBytes[relocStart:relocEnd])

        # should check for text / data / bss overlap

        return cls(text=text,
                   textAddress=textAddress,
                   data=data,
                   bssSize=bssSize,
                   relocs=relocs)

    @classmethod
    def decodeRelocs(cls, bytes):
        """
        Decode in-file relocations and produce a collection of only the interesting ones

        CP/M relocation words map 1:1 to words in the text, then data sections, so address
        can be directly inferred from offset (and we are only supporting contiguous text,data)
        """

        fields = len(bytes) / 2
        relocEntries = struct.unpack('>{}H'.format(fields), bytes)

        relocs = dict()
        size32 = False
        offset = 0
        for reloc in relocEntries:
            outputType = None
            relocType = reloc & RELOC_TYPE_MASK

            # these relocs are all NOPs
            if (relocType == RELOC_TYPE_ABSOLUTE or
                    relocType == RELOC_TYPE_INSTRUCTION):
                pass

            # these all encode the current offset / type
            elif (relocType == RELOC_TYPE_DATA or
                  relocType == RELOC_TYPE_TEXT or
                  relocType == RELOC_TYPE_BSS):

                outputType = relocType

            # this is a prefix for the following reloc
            elif relocType == RELOC_TYPE_UPPER:
                size32 = True
            else:
                # this includes external / pc-relative external relocs, which are only
                # found in linkable objects, not load files.
                raise RuntimeError(
                    'unexpected reloc 0x{:04x}'.format(relocType))

            if outputType is not None:
                if size32:
                    outputType |= RELOC_SIZE_32
                    outputOffset = offset - 2
                else:
                    outputType |= RELOC_SIZE_16
                    outputOffset = offset

                relocs[outputOffset] = outputType

            offset += 2
            if relocType != RELOC_TYPE_UPPER:
                size32 = False

        return relocs

    def _encodeRelocs(self, relocs, outputSize):
        """
        Encode relocations in a format suitable for writing to a file
        """

        relocBytes = bytearray(outputSize)

        for offset in relocs:
            relocSize = relocs[offset] & RELOC_SIZE_MASK
            relocType = relocs[offset] & RELOC_TYPE_MASK

            if relocSize == RELOC_SIZE_32:
                if offset > (outputSize - 4):
                    raise RuntimeError('reloc offset out of bounds: {}:{}'.format(offset, relocs[offset]))

                struct.pack_into('>H', relocBytes, offset, RELOC_TYPE_UPPER)
                offset += 2
            else:
                if offset > (outputSize - 2):
                    raise RuntimeError('reloc offset out of bounds: {}:{}'.format(offset, relocs[offset]))

            struct.pack_into('>H', relocBytes, offset, relocType)

        return relocBytes

    def save(self, fo):
        """
        Write the object to a file
        """

        if (len(self.relocs) > 0) and (self.textAddress != 0):
            raise RuntimeError(
                'cannot write relocatable file with text address != 0')

        header = struct.pack('>HLLLLLLH',
                             TYPE_CONTIG,
                             len(self.text),
                             len(self.data),
                             self.bssSize,
                             0,
                             0,
                             self.textAddress,
                             WITH_RELOCS if len(self.relocs) > 0 else NO_RELOCS)

        fo.write(header)
        fo.write(self.text)
        fo.write(self.data)
        if len(self.relocs) > 0:
            fo.write(self._encodeRelocs(self.relocs, len(self.text) + len(self.data)))

    @property
    def textSize(self):
        return len(self.text)

    @property
    def dataSize(self):
        return len(self.data)

    @property
    def relocSize(self):
        return len(self.relocs)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise RuntimeError('missing name of CP/M executable to inspect')

    fo = open(sys.argv[1], 'rb')
    obj = CPMFile.load(fo)

    emit = 'text 0x{:08x}/0x{:x} data 0x{:08x}/0x{:x} BSS 0x{:08x}/0x{:x}'.format(
        obj.textAddress, len(obj.text),
        obj.dataAddress, len(obj.data),
        obj.bssAddress, obj.bssSize)
    emit += ' reloc {}'.format(len(obj.relocs))
    print(emit)
    print('text')
    hexdump(str(obj.text))
    print('data')
    hexdump(str(obj.data))
    print('reloc')
    for reloc in sorted(obj.relocs):
        print('0x{:08x}: {:05x}'.format(reloc, obj.relocs[reloc]))

