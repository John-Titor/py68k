#
# ELF image loader
#
from bisect import bisect_left
import os
import struct
import subprocess

# note - package is 'pyelftools'
from elftools.elf.constants import SH_FLAGS
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.sections import SymbolTableSection

R_68K_32 = 0x01


class ELFImage(object):
    """
    Program image in the emulator
    """

    def __init__(self, image_filename, symbols_only=False):
        """
        Read the ELF headers and parse the executable
        """
        self._name = os.path.basename(image_filename)

        self._name_cache = dict()       # names are unique, entries are subdicts with 'address' and 'size'
        self._address_cache = dict()    # addresses are not unique, entries are lists of names at that address
        self._symbol_index = None       # sorted list of unique symbol addresses + sentinel

        self._symbols_only = symbols_only
        self._relocation = 0

        self._elf = ELFFile(open(image_filename, "rb"))
        if self._elf.header['e_type'] != 'ET_EXEC':
            raise RuntimeError('not an ELF executable file')
        if self._elf.header['e_machine'] != 'EM_68K':
            raise RuntimeError('not an M68K ELF file')
        if self._elf.num_segments() == 0:
            raise RuntimeError('no segments in ELF file')

        # build the symbol cache
        for section in self._elf.iter_sections():
            if isinstance(section, SymbolTableSection):
                self._cache_symbols(section)

        # look for a stack
        stack_size = None
        if not self._symbols_only:
            for segment in self._elf.iter_segments():
                if segment['p_type'] == 'PT_GNU_STACK':
                    stack_size = segment['p_memsz']
            if stack_size is None:
                raise RuntimeError(f'no stack defined in {self._name} - did you forget to link with -z stack-size=VALUE?')
            else:
                try:
                    stack_base = self._name_cache['_end']['address']
                except KeyError:
                    raise RuntimeError('no _end symbol, cannot locate stack')
                self._add_symbol('__STACK__', stack_base, stack_size)

        # sort symbol addresses to make index
        self._symbol_index = sorted(self._address_cache.keys())
        if len(self._symbol_index) == 0:
            raise RuntimeError(f'no symbols in {image_filename}')

    def _add_symbol(self, name, address, size):
        self._name_cache[name] = {'address': address, 'size': size}
        try:
            self._address_cache[address].append(name)
        except KeyError:
            self._address_cache[address] = [name]

    def _get_loadable_sections(self):
        if self._symbols_only:
            raise RuntimeError(f'loaded for symbols-only')
        loadable_sections = dict()
        for section in self._elf.iter_sections():
            if section['sh_flags'] & SH_FLAGS.SHF_ALLOC:
                loadable_sections[section['sh_addr']] = bytearray(section.data())
        return loadable_sections

    def relocate(self, relocation):
        # find sections that we want to load
        loadable_sections = self._get_loadable_sections()

        # iterate relocation sections
        did_relocate = False
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

                # find the section containing the address that needs to be fixed up
                reloc_address = reloc['r_offset']
                for sec_base, sec_data in loadable_sections.items():
                    sec_offset = reloc_address - sec_base
                    if (sec_base <= reloc_address) and (sec_offset < len(sec_data)):
                        unrelocated_value = struct.unpack_from('>L', sec_data, sec_offset)[0]
                        struct.pack_into('>L', sec_data, sec_offset, unrelocated_value + relocation)
                        did_relocate = True
                        break

        if not did_relocate:
            raise RuntimeError(f'no relocations in {self._name} - did you forget to link with --emit-relocs?')

        relocated_sections = dict()
        for sec_base, sec_data in loadable_sections.items():
            relocated_sections[sec_base + relocation] = sec_data

        self._relocation = relocation
        return relocated_sections

    @property
    def entrypoint(self):
        if self._symbols_only:
            raise RuntimeError(f'loaded for symbols-only')
        return self._elf.header['e_entry'] + self._relocation

    @property
    def initstack(self):
        if self._symbols_only:
            raise RuntimeError(f'loaded for symbols-only')
        if self._stack_size is not None:
            end, _ = self.get_symbol_range('_end')
            return end + self._relocation + self._stack_size

    def _cache_symbols(self, section):

        for nsym, symbol in enumerate(section.iter_symbols()):

            s_name = str(symbol.name)
            if len(s_name) == 0:
                continue
            s_type = symbol['st_info']['type']
            if s_type == 'STT_FILE':
                continue
            s_addr = symbol['st_value']
            s_size = symbol['st_size']

            self._name_cache[s_name] = {'address': s_addr, 'size': s_size}
            try:
                self._address_cache[s_addr].append(s_name)
            except KeyError:
                self._address_cache[s_addr] = [s_name]

    def get_symbol_range(self, name):
        try:
            addr = self._name_cache[name]['address'] + self._relocation
            size = self._name_cache[name]['size']
        except KeyError:
            try:
                addr = int(name)
                size = 1
            except Exception:
                raise RuntimeError(f'no symbol {name}'.format(name))

        return addr, size + addr

    def get_symbol_name(self, address):
        address -= self._relocation
        if address in self._address_cache:
            return ','.join(self._address_cache[address])
        index = bisect_left(self._symbol_index, address)
        if not index:
            return None
        symbol_address = self._symbol_index[index - 1]
        if address < symbol_address:
            return None
        names = list()
        for name in self._address_cache[symbol_address]:
            if (address - symbol_address) < self._name_cache[name]['size']:
                names.append(name)
        if len(names) > 0:
            label = ','.join(names) + f'+{address - symbol_address:#x}'
            return label
        return None
