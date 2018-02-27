#!/usr/bin/env python
#
# CP/M 68K executable format tools
#

import struct
import sys
import os


class CPMFile(object):
    """
    A CPM executable or object file
    """

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

    def __init__(self, withFile=None):
        self.text = None
        self.textAddress = 0

        self.data = None
        self.dataAddress = 0

        self.bssSize = 0
        self.bssAddress = 0

        self._sym = None

        self._textRelocs = None
        self._dataRelocs = None

        if withFile is not None:
            self._load(withFile)

    def _load(self, fo):
        """
        Parse a CP/M 68K executable and load the interesting parts
        """

        fileBytes = bytearray(fo.read())

        # get the filetype
        magic = struct.unpack('>H', fileBytes[0:2])
        if magic[0] == self.TYPE_CONTIG:
            fmt = '>HLLLLLLH'
        elif magic[0] == self.TYPE_NONCONTIG:
            fmt = '>HLLLLLLHLL'
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

        if fields[7] == self.WITH_RELOCS:
            textRelocStart = symtabEnd
            textRelocEnd = textRelocStart + textSize

            dataRelocStart = textRelocEnd
            dataRelocEnd = dataRelocStart + dataSize
        else:
            dataRelocEnd = symtabEnd

        # check filesize
        if dataRelocEnd > len(fileBytes):
            raise RuntimeError('header / file size mismatch')

        # build out our internal representation of the file
        self.text = fileBytes[textStart:textEnd]
        self.textAddress = fields[6]

        self.data = fileBytes[dataStart:dataEnd]
        if magic[0] == self.TYPE_CONTIG:
            self.dataAddress = self.textAddress + textSize
        else:
            self.dataAddress = fields[8]

        self.bssSize = fields[3]
        if magic[0] == self.TYPE_CONTIG:
            self.bssAddress = self.dataAddress + dataSize
        else:
            self.bssAddress = fields[9]

        if symtabSize > 0:
            self._sym = fileBytes[symtabStart:symtabEnd]

        if fields[7] == self.WITH_RELOCS:
            if self.textAddress > 0:
                print 'WARNING: relocatable file but text address != 0'
            self._textRelocs = self._decodeRelocs(
                fileBytes[textRelocStart:textRelocEnd])
            self._dataRelocs = self._decodeRelocs(
                fileBytes[dataRelocStart:dataRelocEnd])

        # should check for text / data / bss overlap

    def _decodeRelocs(self, bytes):
        """
        Decode in-file relocations and produce a collection of only the interesting ones
        """

        fields = len(bytes) / 2
        relocs = struct.unpack('>{}H'.format(fields), bytes)

        output = dict()
        size32 = False
        offset = 0
        for reloc in relocs:
            outputType = None
            relocType = reloc & self.RELOC_TYPE_MASK

            # these relocs are all NOPs
            if (relocType == self.RELOC_TYPE_ABSOLUTE or
                    relocType == self.RELOC_TYPE_INSTRUCTION):
                pass

            # these all encode the current offset / type
            elif (relocType == self.RELOC_TYPE_DATA or
                  relocType == self.RELOC_TYPE_TEXT or
                  relocType == self.RELOC_TYPE_BSS):

                outputType = relocType

            # this is a prefix for the following reloc
            elif relocType == self.RELOC_TYPE_UPPER:
                size32 = True
            else:
                # this includes external / pc-relative external relocs, which are only
                # found in linkable objects, not load files.
                raise RuntimeError(
                    'unexpected reloc 0x{:04x}'.format(relocType))

            if outputType is not None:
                if size32:
                    outputType |= self.RELOC_SIZE_32
                    outputOffset = offset - 2
                else:
                    outputType |= self.RELOC_SIZE_16
                    outputOffset = offset

                output[outputOffset] = outputType

            offset += 2
            if relocType != self.RELOC_TYPE_UPPER:
                size32 = False

        return output

    def _encodeRelocs(self, relocs, sectionSize):
        """
        Encode relocations in a format suitable for writing to a file
        """

        relocBytes = bytearray(sectionSize)

        for offset in relocs:
            relocSize = reloc[offset] & self.RELOC_SIZE_MASK
            relocType = reloc[offset] & self.RELOC_TYPE_MASK

            if relocSize == RELOC_SIZE_32:
                struct.pack_into('>H', relocBytes, self.RELOC_TYPE_UPPER)
                offset += 2

            struct.pack_into('>H', relocBytes, relocType)

        return relocBytes

    def save(self, fd):
        """
        Write the object to a file
        """

        if self._sym is None:
            symLen = 0
        else:
            symLen = len(self._sym)

        if (self._textRelocs is not None) and (self.textAddress != 0):
            raise RuntimeError(
                'cannot write relocatable file with text address != 0')

        # if data / BSS are contiguous, use the compact format
        if ((self.dataAddress == (self.textAddress + len(self.text))) and
                (self.bssAddress == (self.textAddress + len(self.text) + len(self.data)))):
            self.dataAddress = 0
            self.bssAddress = 0

        if self.dataAddress == 0:
            if self.bssAddress != 0:
                raise RuntimeError(
                    'must specify data address if bss address is not zero')

            header = struct.pack('>HLLLLLH',
                                 cls.TYPE_CONTIG,
                                 len(self.text),
                                 len(self.data),
                                 self.bssSize,
                                 symLen,
                                 0,
                                 self.textAddress,
                                 0 if self._textRelocs is not None else 0xffff)
        else:
            if self.bssAddress == 0:
                self.bssAddress = self.dataAddress + len(self.data)

            header = struct.pack('>HLLLLLHLL',
                                 cls.TYPE_NONCONTIG,
                                 len(self.text),
                                 len(self.data),
                                 self.bssSize,
                                 symLen,
                                 0,
                                 self.textAddress,
                                 0 if self._textRelocs is not None else 0xffff,
                                 self._data.address,
                                 self._bss.address)

        fd.write(header)
        fd.write(self.text)
        fd.write(self.data)
        if self._sym is not None:
            fd.write(self._sym)
        if self._textRelocs is not None:
            fd.write(self._encodeRelocs(self._textRelocs, len(self.text)))
            fd.write(self._encodeRelocs(self._dataRelocs, len(self.data)))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise RuntimeError('missing name of CP/M executable to inspect')

    fo = open(sys.argv[1], 'rb')
    obj = CPMFile(fo)

    emit = 'text 0x{:08x}/{} data 0x{:08x}/{} BSS 0x{:08x}/{} '.format(
        obj.textAddress, len(obj.text),
        obj.dataAddress, len(obj.data),
        obj.bssAddress, obj.bssSize)
    if obj._sym is not None:
        emit += ' sym {}'.format(len(obj._sym))
    if obj._textRelocs is not None:
        emit += ' treloc {}'.format(len(obj._textRelocs))
    if obj._dataRelocs is not None:
        emit += ' dreloc {}'.format(len(obj._dataRelocs))

    print emit
