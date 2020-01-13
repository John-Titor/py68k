#
# ELF image loader
#
import os
import subprocess
from bisect import bisect

from musashi.m68k import (
    mem_ram_write_block
)

# note - package is 'pyelftools'
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.enums import ENUM_P_TYPE_BASE
from elftools.elf.constants import SH_FLAGS
from elftools.elf.descriptions import (
    describe_e_machine,
    describe_e_type
)


class image(object):
    """
    Program image in the emulator
    """

    def __init__(self, emu, image_filename):
        """
        Read the ELF headers and prepare to load the executable
        """

        self._emu = emu
        self._lineinfo_cache = dict()
        self._symbol_cache = dict()
        self._address_cache = dict()
        self._addr2line = self._findtool('addr2line')
        self._text_base = 0
        self._text_end = 0
        self._low_sym = 0xffffffff
        self._high_sym = 0
        self._image_filename = image_filename

        if self._addr2line is None:
            raise RuntimeError(
                "unable to find m68k addr2line, check your PATH")

        elf_fd = open(self._image_filename, "rb")
        self._elf = ELFFile(elf_fd)

        if self._elf.header['e_type'] != 'ET_EXEC':
            raise RuntimeError('not an ELF executable file')
        if self._elf.header['e_machine'] != 'EM_68K':
            raise RuntimeError('not an M68K ELF file')
        if self._elf.num_segments() == 0:
            raise RuntimeError('no segments in ELF file')

        # iterate sections
        for section in self._elf.iter_sections():

            # does this section need to be loaded?
            if section['sh_flags'] & SH_FLAGS.SHF_ALLOC:
                p_vaddr = section['sh_addr']
                p_paddr = p_vaddr
                p_size = section['sh_size']

                # load address may not equal run address, but the section 
                # doesn't know that
                for segment in self._elf.iter_segments():
                    if segment.section_in_segment(section):
                        if segment['p_paddr'] != 0:
                            p_paddr -= segment['p_vaddr'] - segment['p_paddr']
                            break

                self._emu.log(f'{section.name} 0x{p_vaddr:x}/{p_size} @ 0x{p_paddr:x}')

                # XXX should really be a call on the emulator
                mem_ram_write_block(p_paddr, p_size, section.data())

                if section.name == '.text':
                    self._text_base = p_paddr
                    self._text_end = p_paddr + p_size

            # does it contain symbols?
            if isinstance(section, SymbolTableSection):
                self._cache_symbols(section)

        self._symbol_index = sorted(self._symbol_cache.keys())

    def _cache_symbols(self, section):

        for nsym, symbol in enumerate(section.iter_symbols()):

            # only interested in data and function symbols
            s_type = symbol['st_info']['type']
            if s_type != 'STT_OBJECT' and s_type != 'STT_FUNC':
                continue

            s_addr = symbol['st_value']
            s_size = symbol['st_size']
            s_name = str(symbol.name)

            self._low_sym = min(s_addr, self._low_sym)
            self._high_sym = max(s_addr + s_size, self._high_sym)

            self._symbol_cache[s_addr] = {'name': s_name, 'size': s_size}
            self._address_cache[s_name] = s_addr

    def _findtool(self, tool):
        for prefix in ['m68k-elf-', 'm68k-unknown-elf-']:
            for path in os.environ['PATH'].split(os.pathsep):
                path = path.strip('"')
                candidate = os.path.join(path, prefix + tool)
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate
                else:
                    print(f"no {candidate}")
        return None

    def lineinfo(self, addr):
        try:
            return self._lineinfo_cache[addr]

        except KeyError:

            # -i gives extra information about inlined functions, but it puts
            # newlines in the result that mess up the log...

            symb = subprocess.Popen([self._addr2line,
                                     '-pfC',
                                     '-e',
                                     self._image_filename,
                                     '{:#x}'.format(addr)],
                                    stdout=subprocess.PIPE)
            output, err = symb.communicate()

            result = output.decode('ascii')
            self._lineinfo_cache[addr] = result
            return result

    def symname(self, addr):
        if addr < self._low_sym or addr >= self._high_sym:
            return ''

        try:
            return self._symbol_cache[addr]['name']

        except KeyError:
            # look for the next highest symbol address
            pos = bisect(self._symbol_index, addr)
            if pos == 0:
                # address lower than anything we know
                return ''
            insym = self._symbol_index[pos - 1]

            # check that the value is within the symbol
            delta = addr - insym
            if self._symbol_cache[insym]['size'] <= delta:
                return ''

            # it is, construct a name + offset string
            name = '{}+{:#x}'.format(self._symbol_cache[insym]['name'], delta)

            # add it to the symbol cache
            self._symbol_cache[addr] = {'name': name, 'size': 1}

            return name

    def symrange(self, name):
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

    def check_text(self, addr):
        if addr < self._text_base or addr >= self._text_end:
            return False
        return True
