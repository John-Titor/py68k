#!/usr/bin/env python
#
# Convert uCLinux m68k 'bFLT' to CPM 68k executable
#

import blft
import cpm

relocTypeMappings = {
    bflt.RELOC_TEXT: cpm.RELOC_TYPE_TEXT | cpm.RELOC_SIZE_32,
    bflt.RELOC_DATA: cpm.RELOC_TYPE_DATA | cpm.RELOC_SIZE_32,
    bflt.RELOC_BSS: cpm.RELOC_TYPE_BSS | cpm.RELOC_SIZE_32
}


def translateRelocs(bfltRelocs):
    cpmRelocs = dict()
    for address in bfltRelocs:
        cpmRelocs[address] = relocTypeMappings[bfltRelocs[address]]
