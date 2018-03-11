#!/usr/bin/env python
#
# Convert m68k ELF to CP/M-68K executable
#

import sys
import os
import argparse
import elf
import cpm


def translateRelocs(elfRelocs):
    relocTypeMappings = {
        elf.R_TEXT | elf.R_68K_32: cpm.RELOC_TYPE_TEXT | cpm.RELOC_SIZE_32,
        elf.R_TEXT | elf.R_68K_16: cpm.RELOC_TYPE_TEXT | cpm.RELOC_SIZE_16,

        elf.R_DATA | elf.R_68K_32: cpm.RELOC_TYPE_DATA | cpm.RELOC_SIZE_32,
        elf.R_DATA | elf.R_68K_16: cpm.RELOC_TYPE_DATA | cpm.RELOC_SIZE_16,

        elf.R_BSS | elf.R_68K_32: cpm.RELOC_TYPE_BSS | cpm.RELOC_SIZE_32,
        elf.R_BSS | elf.R_68K_16: cpm.RELOC_TYPE_BSS | cpm.RELOC_SIZE_16
    }

    cpmRelocs = dict()
    for address in elfRelocs:
        if not elfRelocs[address] in relocTypeMappings:
            raise RuntimeError('unhandled ELF relocation 0x{:x}'.format(elfRelocs[address]))
        cpmRelocs[address] = relocTypeMappings[elfRelocs[address]]

    return cpmRelocs


parser = argparse.ArgumentParser(description='ELF to CP/M-68K executable converter')
parser.add_argument('inputFile',
                    type=str,
                    help='the source file to be converted')
parser.add_argument('outputFile',
                    type=str,
                    help='the destination file to be produced')
args = parser.parse_args()

elfFo = open(args.inputFile, 'rb')
elfImage = elf.ELFLoader.load(elfFo)

cpmImage = cpm.CPMFile(text=elfImage.text,
                       textAddress=0,
                       data=elfImage.data,
                       bssSize=elfImage.bssSize,
                       relocs=translateRelocs(elfImage.relocs))

cpmFo = open(args.outputFile, 'wb')
cpmImage.save(cpmFo)
