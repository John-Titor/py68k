# Tracing support

from imageELF import ELFImage
from musashi import m68k


class Trace(object):

    registers = {
        'D0': m68k.REG_D0,
        'D1': m68k.REG_D1,
        'D2': m68k.REG_D2,
        'D3': m68k.REG_D3,
        'D4': m68k.REG_D4,
        'D5': m68k.REG_D5,
        'D6': m68k.REG_D6,
        'D7': m68k.REG_D7,
        'A0': m68k.REG_A0,
        'A1': m68k.REG_A1,
        'A2': m68k.REG_A2,
        'A3': m68k.REG_A3,
        'A4': m68k.REG_A4,
        'A5': m68k.REG_A5,
        'A6': m68k.REG_A6,
        'A7': m68k.REG_A7,
        'PC': m68k.REG_PC,
        'SR': m68k.REG_SR,
        'SP': m68k.REG_SP,
        'USP': m68k.REG_USP,
        'SSP': m68k.REG_ISP,
    }

    operation_map = {
        m68k.MEM_READ: 'READ',
        m68k.MEM_WRITE: 'WRITE',
        m68k.INVALID_READ: 'BAD_READ',
        m68k.INVALID_WRITE: 'BAD_WRITE',
        m68k.MEM_MAP: 'MAP'
    }

    __global_tracer = None
    __emu = None

    def __init__(self, args, emulator):
        if Trace.__global_tracer is None:
            Trace.__global_tracer = self
            Trace.__emu = emulator
        else:
            raise RuntimeError('cannot have more than one Trace instance')

        self._trace_file = open(args.trace_file, "w", 1)
        self._trace_memory = False
        self._trace_instructions = False
        self._trace_jumps = False

        self._symbol_files = list()

        m68k.mem_set_trace_handler(self.cb_trace_memory)
        m68k.mem_set_instr_handler(self.cb_trace_instruction)

        if args.trace_memory or args.trace_everything:
            m68k.mem_enable_mem_tracing(True)
        if args.trace_instructions or args.trace_everything:
            m68k.mem_enable_instr_tracing(True)

        # add symbol files
        if args.symbols is not None:
            for symfile in args.symbols:
                self.add_symbol_image(ELFImage(symfile, symbols_only=True))

    def close(self):
        try:
            self._trace_file.flush()
            self._trace_file.close()
        except Exception:
            pass

    @classmethod
    def get_tracer(cls):
        if cls.__global_tracer is None:
            raise RuntimeError('must create instance before calling get_tracer')
        return cls.__global_tracer

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--trace-file',
                            type=str,
                            default='trace.out',
                            help='file to which trace output will be written')
        parser.add_argument('--trace-everything',
                            action='store_true',
                            help='enable all tracing options')
        parser.add_argument('--trace-memory',
                            action='store_true',
                            help='enable memory tracing')
        parser.add_argument('--trace-instructions',
                            action='store_true',
                            help='enable instruction tracing')
        parser.add_argument('--symbols',
                            type=str,
                            action='append',
                            metavar='ELF-SYMFILE',
                            help='add ELF objects containing symbols for symbolicating trace')

    def trace(self, action='', address=None, info=''):
        """
        Cut a trace entry

        action[10]: address/symbols[40] : info
        """
        if address is not None:
            symname = self._sym_for_address(address)
            if symname is not None:
                afield = '{} / {:#08x}'.format(symname, address)
            else:
                afield = '{:#08x}'.format(address)
        else:
            afield = ''

        self._trace_file.write(f'{action:<10}: {afield:>40} : {info.strip()}\n')

    def enable(self, what, enable):
        if what == 'everything':
            self.enable('memory', enable)
            self.enable('instructions', enable)
        elif what == 'memory':
            m68k.mem_enable_mem_tracing(enable)
        elif what == 'instructions':
            m68k.mem_enable_instr_tracing(enable)
        else:
            raise RuntimeError(f'unknown trace category {what}')

    def log(self, msg):
        self.trace(action='LOG', info=msg)

    def cb_trace_memory(self, operation, addr, size, value):
        """
        Cut a memory trace entry
        """
        try:
            action = self.operation_map[operation]
            if operation == m68k.MEM_MAP:
                if value == m68k.MEM_MAP_RAM:
                    info = f'RAM {size:#x}'
                elif value == m68k.MEM_MAP_ROM:
                    info = f'ROM {size:#x}'
                elif value == m68k.MEM_MAP_DEVICE:
                    info = f'DEVICE {size:#x}'
                else:
                    raise RuntimeError(f'unexpected mapping type {value}')
            else:
                if size == m68k.MEM_SIZE_8:
                    info = f'{value:#04x}'
                elif size == m68k.MEM_SIZE_16:
                    info = f'{value:#06x}'
                elif size == m68k.MEM_SIZE_32:
                    info = f'{value:#010x}'
                else:
                    raise RuntimeError(f'unexpected trace size {size}')

            self.trace(action, addr, info)

        except Exception:
            self.fatal_exception(sys.exc_info())

        return 0

    def cb_trace_instruction(self, pc):
        """
        Cut an instruction trace entry
        """
        try:
            dis = m68k.disassemble(pc, Trace.__emu._cpu_type)
            reg_info = ''
            for reg in self.registers:
                if dis.find(reg) is not -1:
                    reg_info += ' {}={:#x}'.format(reg, m68k.get_reg(self.registers[reg]))

            self.trace(action='EXECUTE', address=pc, info=f'{dis:30} {reg_info}')
            return

        except Exception:
            Trace.__emu.fatal_exception(sys.exc_info())

    def add_symbol_image(self, elfImage):
        self._symbol_files.append(elfImage)

    def _sym_for_address(self, address):
        for symfile in self._symbol_files:
            name = symfile.get_symbol_name(address)
            if name is not None:
                return name
        return None
