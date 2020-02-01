#!/usr/bin/env python
#
# Minimal ELF reader
#
# Note that this is a minimal implementation intended to serve the needs
# of the elf2cpm converter only.
#

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.constants import P_FLAGS, SH_FLAGS
import struct

# relocation types
R_68K_NONE = 0x00
R_68K_32 = 0x01
R_68K_16 = 0x02
R_68K_8 = 0x03
R_68K_PC32 = 4
R_68K_PC16 = 5
R_68K_PC8 = 6
R_68K_GOT32 = 7
R_68K_GOT16 = 8
R_68K_GOT8 = 9
R_68K_GOT32O = 10
R_68K_GOT16O = 11
R_68K_GOT8O = 12
R_68K_PLT32 = 13
R_68K_PLT16 = 14
R_68K_PLT8 = 15
R_68K_PLT32O = 16
R_68K_PLT16O = 17
R_68K_PLT8O = 18
R_68K_COPY = 19
R_68K_GLOB_DAT = 20
R_68K_JMP_SLOT = 21
R_68K_RELATIVE = 22
R_68K_GNU_VTINHERIT = 23
R_68K_GNU_VTENTRY = 24
R_68K_TLS_GD32 = 25
R_68K_TLS_GD16 = 26
R_68K_TLS_GD8 = 27
R_68K_TLS_LDM32 = 28
R_68K_TLS_LDM16 = 29
R_68K_TLS_LDM8 = 30
R_68K_TLS_LDO32 = 31
R_68K_TLS_LDO16 = 32
R_68K_TLS_LDO8 = 33
R_68K_TLS_IE32 = 34
R_68K_TLS_IE16 = 35
R_68K_TLS_IE8 = 36
R_68K_TLS_LE32 = 37
R_68K_TLS_LE16 = 38
R_68K_TLS_LE8 = 39
R_68K_TLS_DTPMOD32 = 40
R_68K_TLS_DTPREL32 = 41
R_68K_TLS_TPREL32 = 42


R_TEXT = 0x000
R_DATA = 0x100
R_BSS = 0x200


class ELFLoader(object):
    """
    Read a simple ELF executable; should be linked with text at 0,
    with relocations, text/data/BSS in ascending address order and reasonably
    contiguous.

    At most one read-execute and one read-write segment are supported; normally
    this should be .text / .data and friends.
    """

    P_FLAGS_MASK = P_FLAGS.PF_X | P_FLAGS.PF_R | P_FLAGS.PF_W
    P_FLAGS_RX = P_FLAGS.PF_X | P_FLAGS.PF_R
    P_FLAGS_RW = P_FLAGS.PF_R | P_FLAGS.PF_W

    def __init__(self, text, data, bssSize, relocs):
        self.text = text
        self.data = data
        self.bssSize = bssSize
        self.relocs = relocs

    @classmethod
    def load(cls, fo):
        ef = ELFFile(fo)

        if ef.header['e_type'] != 'ET_EXEC':
            raise RuntimeError(
                'not an ELF executable file (type {})'.format(ef.header['e_type']))
        if ef.header['e_machine'] != 'EM_68K':
            raise RuntimeError('not an M68K ELF file')
        if ef.num_segments() != 2:
            raise RuntimeError('wrong number of segments in ELF file')

        # Look at segments for text and data; note that we
        # expect to see exactly two segments, one RX, one RW,
        # for text and data respectively, with data immediately
        # following text in memory.

        textSegment = ef.get_segment(0)
        textAddress = textSegment['p_vaddr']
        textSize = textSegment['p_filesz']

        dataSegment = ef.get_segment(1)
        dataAddress = dataSegment['p_vaddr']
        dataSize = dataSegment['p_filesz']

        # Look for BSS sections
        bssAddress = None
        bssLimit = None
        for section in ef.iter_sections():
            if (section['sh_type'] == 'SHT_NOBITS') and (section['sh_flags'] & SH_FLAGS.SHF_ALLOC):

                secStart = section['sh_addr']
                secLimit = section['sh_addr'] + section['sh_size']

                # track low BSS address
                if bssAddress is None:
                    bssAddress = secStart
                elif secStart < bssAddress:
                    bssAddress = secStart

                # track BSS limit
                if bssLimit is None:
                    bssLimit = secLimit
                elif secLimit > bssLimit:
                    bssLimit = secLimit

        if bssAddress is None:
            bssAddress = dataAddress + dataSize
            bssSize = 0
        else:
            bssSize = bssLimit - bssAddress

        # extend text to cover the gap created by data segment alignment
        dataGap = dataAddress - (textAddress + textSize)
        if dataGap < 0:
            raise RuntimeError('data segment before text')
        textSize += dataGap

        # extend data to cover the gap created by BSS alignment
        bssGap = bssAddress - (dataAddress + dataSize)
        if bssGap < 0:
            raise RuntimeError('BSS before data segment (0x{:x} inside/before 0x{:x}/0x{:x}'.format(
                bssAddress, dataAddress, dataSize))
        dataSize += bssGap

        # sanity-check the text and data segments
        if (textSegment['p_type'] != 'PT_LOAD') or (dataSegment['p_type'] != 'PT_LOAD'):
            raise RuntimeError('expected two PT_LOAD segments')

        if (textSegment['p_flags'] & cls.P_FLAGS_MASK) != cls.P_FLAGS_RX:
            raise RuntimeError('text segment is not RX')
        if textAddress != 0:
            raise RuntimeError('text segment is not at 0')

        if (dataSegment['p_flags'] & cls.P_FLAGS_MASK) != cls.P_FLAGS_RW:
            raise RuntimeError('data segment is not RW')
        if dataAddress != textAddress + textSize:
            raise RuntimeError('data segment @ 0x{:x} does not follow text 0x{:x}/0x{:x}'.format(
                dataAddress, textAddress, textSize))

        text = textSegment.data().ljust(textSize, '\0')
        data = dataSegment.data().ljust(dataSize, '\0')

        if len(text) != textSize:
            raise RuntimeError('text size mismatch')
        if len(data) != dataSize:
            raise RuntimeError('data size mismatch')

        print('text 0x{:x} data 0x{:x} bss 0x{:x}'.format(textSize, dataSize, bssSize))

        # look for relocations
        relocs = dict()
        for section in ef.iter_sections():
            if isinstance(section, RelocationSection):

                # what section do these relocations affect?
                relocSection = ef.get_section(section['sh_info'])
                if not (relocSection['sh_flags'] & SH_FLAGS.SHF_ALLOC):
                    # print('Not relocating {}'.format(relocSection.name))
                    continue

                # print('Relocate: {} using {}'.format(relocSection.name, section.name))
                symtab = ef.get_section(section['sh_link'])

                for reloc in section.iter_relocations():
                    relAddress = reloc['r_offset']
                    if relAddress >= (len(text) + len(data)):
                        raise RuntimeError('relocation outside known space')

                    if not reloc.is_RELA():
                        raise RuntimeError('unexpected REL reloc')

                    relType = reloc['r_info_type']

                    # get the symbol table entry the reloc refers to
                    if reloc['r_info_sym'] >= symtab.num_symbols():
                        raise RuntimeError(
                            'symbol reference in relocation out of bounds')
                    relTarget = symtab.get_symbol(reloc['r_info_sym'])['st_value']

                    # It looks like we can ignore the addend, as it's already
                    # present in the object file...
                    relAddend = reloc['r_addend']

                    # Sort out what we're going to do with this relocation...
                    if relType == R_68K_32:
                        pass
                    elif relType == R_68K_NONE:
                        # print('ignoring none-reloc @ 0x{:x}'.format(relAddress))
                        continue
                    elif relType == R_68K_PC32:
                        # print('ignoring PC32 reloc @ 0x{:x} -> 0x{:x}+{:x}'.format(relAddress, relTarget, relAddend))
                        continue
                    elif relType == R_68K_PC16:
                        # print('ignoring PC16 reloc @ 0x{:x} -> 0x{:x}+{:x}'.format(relAddress, relTarget, relAddend))
                        continue
                    elif relType == R_68K_PC8:
                        # print('ignoring PC8 reloc @ 0x{:x} -> 0x{:x}+{:x}'.format(relAddress, relTarget, relAddend))
                        continue
                    else:
                        raise RuntimeError('unexpected relocation type {} @ 0x{:x} -> 0x{:x}+x'.format(relType, relAddress, relTarget, relAddend))

                    # print('RELA address 0x{:08x} target 0x{:x} type {} addend 0x{:x}'.format(relAddress, relTarget, relType, relAddend))

                    if relTarget < len(text):
                        relType |= R_TEXT
                        if relAddend > len(text):
                            raise RuntimeError('addend outside of text section')
                    elif relTarget < (len(text) + len(data)):
                        relType |= R_DATA
                        if relAddend > len(text):
                            raise RuntimeError('addend outside of data section')
                    elif relTarget <= (len(text) + len(data) + bssSize):
                        # note, <= to allow pointer to _end, which is immediately *after* the BSS
                        relType |= R_BSS
                        if relAddend > bssSize:
                            raise RuntimeError('addend outside of bss section')
                    else:
                        raise RuntimeError(
                            'relocation target not in known space')

                    # print('    -> type 0x{:03x}'.format(relType))

                    if relAddress < len(text):
                        inSeg = text
                        segOffset = relAddress
                    elif relAddress < (len(text) + len(data)):
                        inSeg = data
                        segOffset = relAddress - len(text)
                    else:
                        raise RuntimeError('relocation not in known space')

                    unRelocated = struct.unpack('>L', inSeg[segOffset:segOffset+4])[0]
                    # print('    unrelocated: 0x{:x}'.format(unRelocated))

                    if unRelocated != (relTarget + relAddend):
                        raise RuntimeError("unrelocated field 0x{:x} != target 0x{:x} + addend 0x{:x}".format(unRelocated, relTarget, relAddend))

                    relocs[relAddress] = relType

        return cls(text=text,
                   data=data,
                   bssSize=bssSize,
                   relocs=relocs)
