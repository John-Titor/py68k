#!/usr/bin/env python
#
# Convert uCLinux m68k 'bFLT' to CPM 68k executable
#

import sys, os, argparse
import blft
import cpm

def translateRelocs(bfltRelocs):
	relocTypeMappings = {
	    bflt.RELOC_TEXT: cpm.RELOC_TYPE_TEXT | cpm.RELOC_SIZE_32,
	    bflt.RELOC_DATA: cpm.RELOC_TYPE_DATA | cpm.RELOC_SIZE_32,
	    bflt.RELOC_BSS: cpm.RELOC_TYPE_BSS | cpm.RELOC_SIZE_32
	}

    cpmRelocs = dict()
    for address in bfltRelocs:
        cpmRelocs[address] = relocTypeMappings[bfltRelocs[address]]

    return cpmRelocs()


parser = argparse.ArgumentParser(description='uCLinux bFLT to CP/M-68K executable converter')
parser.add_argument('inputFile',
					required=True,
					type=str,
					help='the source file to be converted')
parser.add_argument('outputFile',
					required=True,
					type=str,
					help='the destination file to be produced')
args = parser.parse_args()

bfltFo = open(args.inputFile, 'rb')
bfltImage = bflt.BFLTFile(bfltFo)

cpmImage = cpm.CPMFile(text=bfltImage.text,
					   textAddress=0,
					   data=bfltImage.data,
					   bssSize=bfltImage.bssSize,
					   relocs=translateRelocs(bfltImage.relocs))


cpmFile = open(args.outputFile, 'wb')



