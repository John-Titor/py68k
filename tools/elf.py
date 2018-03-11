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

R_68K_32 = 0x01
R_68K_16 = 0x02
R_68K_8 = 0x03

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

        # look for relocations
        relocs = dict()
        for section in ef.iter_sections():
            if isinstance(section, RelocationSection):
                symtab = ef.get_section(section['sh_link'])

                for reloc in section.iter_relocations():

                    if not reloc.is_RELA():
                        raise RuntimeError('unexpected REL reloc')

                    # get the symbol table entry the reloc refers to
                    if reloc['r_info_sym'] >= symtab.num_symbols():
                        raise RuntimeError(
                            'symbol reference in relocation out of bounds')
                    relAddress = reloc['r_offset']
                    relTarget = symtab.get_symbol(reloc['r_info_sym'])['st_value']
                    relType = reloc['r_info_type']
                    relAddend = reloc['r_addend']

                    if relAddend != 0:
                        raise RuntimeError('cannot handle non-zero addend')

                    print("RELA address 0x{:x} target 0x{:x} type {} addend {}".format(relAddress, relTarget, relType, relAddend))

                    if relTarget < len(text):
                        relType |= R_TEXT
                    elif relTarget < (len(text) + len(data)):
                        relType |= R_DATA
                    elif relTarget < (len(text) + len(data) + bssSize):
                        relType |= R_BSS
                    else:
                        raise RuntimeError(
                            'relocation target not in known space')

                    relocs[relAddress] = relType

        return cls(text=text,
                   data=data,
                   bssSize=bssSize,
                   relocs=relocs)
