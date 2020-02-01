#
# ELF image loader
#
import os
import subprocess
from bisect import bisect

# note - package is 'pyelftools'
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.enums import ENUM_P_TYPE_BASE
from elftools.elf.constants import SH_FLAGS
from elftools.elf.descriptions import (
    describe_e_machine,
    describe_e_type
)
from elftools.dwarf.descriptions import describe_form_class


class ELFImage(object):
    """
    Program image in the emulator
    """

    def __init__(self, image_filename):
        """
        Read the ELF headers and parse the executable
        """
        self._address_info_cache = dict()
        self._symbol_cache = dict()
        self._address_cache = dict()
        self._elf = ELFFile(open(image_filename, "rb"))
        self._name = os.path.basename(image_filename)

        if self._elf.header['e_type'] != 'ET_EXEC':
            raise RuntimeError('not an ELF executable file')
        if self._elf.header['e_machine'] != 'EM_68K':
            raise RuntimeError('not an M68K ELF file')
        if self._elf.num_segments() == 0:
            raise RuntimeError('no segments in ELF file')

        if not self._elf.has_dwarf_info():
            raise RuntimeError('no DWARF info in ELF file')
        self._dwarf = self._elf.get_dwarf_info()

        # iterate sections
        for section in self._elf.iter_sections():

            # does it contain symbols?
            if isinstance(section, SymbolTableSection):
                self._cache_symbols(section)

        self._symbol_index = sorted(self._symbol_cache.keys())

    def _get_loadable_sections(self):
        loadable_sections = dict()
        for section in self._elf.iter_sections():
            if section['sh_flags'] & SH_FLAGS.SHF_ALLOC:
                loadable_sections[section['sh_addr']] = bytearray(section.data())
        return loadable_sections

    def relocate(self, offset):
        # find sections that we want to load
        loadable_sections = self._get_loadable_sections()

        # iterate relocation sections
        for section in self._elf.iter_sections():
            if not isinstance(section, RelocationSection):
                continue

            # do these relocates affect a loaded section?
            reloc_section = self._elf.get_section(section['sh_info'])
            if not (reloc_section['sh_flags'] & SH_FLAGS.SHF_ALLOC):
                continue

            # iterate relocations
            for reloc in section.iter_relocations():
                if not reloc.is_RELA():
                    raise RuntimeError('unexpected REL reloc')

                # Only R_68K_32 relocations are of interest
                if reloc['r_info_type'] != R_68K_32:
                    continue

                reloc_address = reloc['r_offset']
                rel_value = offset + reloc['r_addend']

                for sec_base, sec_data in loadable_sections.items():
                    sec_offset = reloc_address - sec_base
                    if (sec_base <= reloc_address) and (sec_offset < len(sec_data)):
                        sec_data[sec_offset + 0] = rel_value >> 24
                        sec_data[sec_offset + 1] = rel_value >> 16
                        sec_data[sec_offset + 2] = rel_value >> 8
                        sec_data[sec_offset + 3] = rel_value >> 0
                        break

        relocated_sections = dict()
        for sec_base, sec_data in loadable_sections.items():
            relocated_sections[sec_base + offset] = sec_data

        return (self._elf.header['e_entry'] + offset, relocated_sections)

    def _cache_symbols(self, section):

        for nsym, symbol in enumerate(section.iter_symbols()):

            # only interested in data and function symbols
            s_type = symbol['st_info']['type']
            if s_type != 'STT_OBJECT' and s_type != 'STT_FUNC':
                continue

            s_addr = symbol['st_value']
            s_size = symbol['st_size']
            s_name = str(symbol.name)

            self._symbol_cache[s_addr] = {'name': s_name, 'size': s_size}
            self._address_cache[s_name] = s_addr

    def get_symbol_range(self, name):
        try:
            addr = self._address_cache[name]
            size = self._symbol_cache[addr]['size']
        except KeyError:
            try:
                addr = int(name)
                size = 1
            except Exception:
                raise RuntimeError(
                    'can\'t find a symbol called {} and can\'t convert it to an address'.format(name))

        return range(addr, addr + size)

    def get_address_info(self, address):
        # return a triple of file, line, function for a given address
        try:
            return self._address_info_cache[address]
        except KeyError:
            function = self._function_for_address(address)
            filename, line = self._fileinfo_for_address(address)
            self._address_info_cache[address] = (filename, line, function)
            return (filename, line, function)

    def _function_for_address(self, address):
        # Go over all DIEs in the DWARF information, looking for a subprogram
        # entry with an address range that includes the given address. Note that
        # this simplifies things by disregarding subprograms that may have
        # split address ranges.
        for CU in self._dwarf.iter_CUs():
            for DIE in CU.iter_DIEs():
                try:
                    if DIE.tag == 'DW_TAG_subprogram':
                        lowpc = DIE.attributes['DW_AT_low_pc'].value

                        # DWARF v4 in section 2.17 describes how to interpret the
                        # DW_AT_high_pc attribute based on the class of its form.
                        # For class 'address' it's taken as an absolute address
                        # (similarly to DW_AT_low_pc); for class 'constant', it's
                        # an offset from DW_AT_low_pc.
                        highpc_attr = DIE.attributes['DW_AT_high_pc']
                        highpc_attr_class = describe_form_class(highpc_attr.form)
                        if highpc_attr_class == 'address':
                            highpc = highpc_attr.value
                        elif highpc_attr_class == 'constant':
                            highpc = lowpc + highpc_attr.value
                        else:
                            print('Error: invalid DW_AT_high_pc class:',
                                  highpc_attr_class)
                            continue

                        if lowpc <= address <= highpc:
                            return DIE.attributes['DW_AT_name'].value
                except KeyError:
                    continue
        return None

    def _fileinfo_for_address(self, address):
        # Go over all the line programs in the DWARF information, looking for
        # one that describes the given address.
        for CU in self._dwarf.iter_CUs():
            # First, look at line programs to find the file/line for the address
            lineprog = self._dwarf.line_program_for_CU(CU)
            prevstate = None
            for entry in lineprog.get_entries():
                # We're interested in those entries where a new state is assigned
                if entry.state is None:
                    continue
                if entry.state.end_sequence:
                    # if the line number sequence ends, clear prevstate.
                    prevstate = None
                    continue
                # Looking for a range of addresses in two consecutive states that
                # contain the required address.
                if prevstate and prevstate.address <= address < entry.state.address:
                    filename = lineprog['file_entry'][prevstate.file - 1].name
                    line = prevstate.line
                    return filename, line
                prevstate = entry.state
        return None, None