import time
import sys
import signal
import traceback

from imageELF import ELFImage
from device import RootDevice
from musashi import m68k


class Emulator(object):

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

    cpu_map = {
        '68000': m68k.CPU_TYPE_68000,
        '68010': m68k.CPU_TYPE_68010,
        '68EC020': m68k.CPU_TYPE_68EC020,
        '68020': m68k.CPU_TYPE_68020,
        '68EC030': m68k.CPU_TYPE_68EC030,
        '68030': m68k.CPU_TYPE_68030,
        '68EC040': m68k.CPU_TYPE_68EC040,
        '68LC040': m68k.CPU_TYPE_68LC040,
        '68040': m68k.CPU_TYPE_68040,
        'SCC68070': m68k.CPU_TYPE_SCC68070,
    }

    operation_map = {
        m68k.MEM_READ: 'READ',
        m68k.MEM_WRITE: 'WRITE',
        m68k.INVALID_READ: 'BAD_READ',
        m68k.INVALID_WRITE: 'BAD_WRITE',
        m68k.MEM_MAP: 'MAP'
    }

    def __init__(self, args, cpu="68000", frequency=8000000):

        self._dead = False
        self._exception_info = None
        self._postmortem = None
        self._root_device = None

        # initialise tracing
        self._trace_file = open(args.trace_file, "w", 1)
        self._trace_memory = False
        self._trace_instructions = False
        self._trace_jumps = False

        # files and symbolication
        self._load_image = None
        self._symbol_files = list()

        # time
        self._cpu_frequency = frequency
        self._elapsed_cycles = 0
        self._device_deadline = 0
        self._default_quantum = int(self._cpu_frequency / 1000)  # ~1ms in cycles
        self._device_tick_deadline = 0

        # reset callbacks
        self._reset_hooks = list()

        # intialise the CPU
        try:
            self._cpu_type = self.cpu_map[cpu]
        except KeyError:
            raise RuntimeError(f"unsupported CPU: {cpu}")
        m68k.set_cpu_type(self._cpu_type)
        m68k.cpu_init()

        # attach unconditional callback functions
        m68k.set_reset_instr_callback(self.cb_reset)
        m68k.set_illg_instr_callback(self.cb_illg)

        # set tracing options
        if args.trace_memory or args.trace_everything:
            self.trace_enable('memory')
        if args.trace_instructions or args.trace_everything:
            self.trace_enable('instructions')
        if args.trace_jumps or args.trace_everything:
            self.trace_enable('jumps')
        if args.trace_exceptions or args.trace_everything:
            self.trace_enable('exceptions')

        if args.cycle_limit > 0:
            self._cycle_limit = args.cycle_limit
        else:
            self._cycle_limit = sys.maxsize

        # load an executable?
        if args.load is not None:
            self._load_image = ELFImage(args.load)
            self._symbol_files.append(self._load_image)
            self._load_address = args.load_address

        # add symbol files
        if args.symbols is not None:
            for symfile in args.symbols:
                self._symbol_files.append(ELFImage(symfile))

        # wire up the root device
        self.add_device(args, RootDevice)

    @classmethod
    def add_arguments(cls, parser, default_load_address=0x400):

        parser.add_argument('--trace-file',
                            type=str,
                            default='trace.out',
                            help='file to which trace output will be written')
        parser.add_argument('--cycle-limit',
                            type=int,
                            default=float('inf'),
                            metavar='CYCLES',
                            help='stop the emulation after CYCLES machine cycles')
        parser.add_argument('--trace-everything',
                            action='store_true',
                            help='enable all tracing options')
        parser.add_argument('--trace-memory',
                            action='store_true',
                            help='enable memory tracing at startup')
        parser.add_argument('--trace-instructions',
                            action='store_true',
                            help='enable instruction tracing at startup (implies --trace-jumps)')
        parser.add_argument('--trace-jumps',
                            action='store_true',
                            help='enable branch tracing at startup')
        parser.add_argument('--trace-exceptions',
                            action='store_true',
                            help='enable tracing all exceptions at startup')
        parser.add_argument('--symbols',
                            type=str,
                            action='append',
                            metavar='ELF-SYMFILE',
                            help='add ELF objects containing symbols for symbolicating trace')
        parser.add_argument('--load',
                            type=str,
                            metavar='ELF-PROGRAM',
                            help='load an ELF program (may require ROM load to be disabled)')
        parser.add_argument('--load-address',
                            type=int,
                            metavar='LOAD-ADDRESS',
                            default=default_load_address,
                            help='relocate loaded ELF programs to this address before running')

    def loadImage(self, image_filename):
        try:
            suffix = image_filename.split('.')[1].lower()
        except Exception:
            raise RuntimeError(f"image filename '{image_filename}' must have an extension")

        if suffix == "elf":
            image = imageELF.image(self, image_filename)
        elif suffix == "bin":
            image = imageBIN.image(self, image_filename)
        else:
            raise RuntimeError(f"image filename '{image.filename}' must end in .elf or .bin")

        return image

    def run(self):
        if self._load_image is not None:
            # relocate to the load address & write to memory
            sections = self._load_image.relocate(self._load_address)
            for section_address, section_data in sections.items():
                m68k.mem_write_bulk(section_address, section_data)

            # patch the initial stack and entrypoint
            _, stack_limit = self._load_image.get_symbol_range('__STACK__')
            if stack_limit is not None:
                m68k.mem_write_memory(0x0, m68k.MEM_SIZE_32, stack_limit)
            m68k.mem_write_memory(0x4, m68k.MEM_SIZE_32, self._load_image.entrypoint)

        signal.signal(signal.SIGINT, self._keyboard_interrupt)
        print('\nHit ^C to exit\n')

        # reset everything
        self.cb_reset()

        # reset the CPU ready for execution
        m68k.pulse_reset()

        self._start_time = time.time()
        while not self._dead:
            self._root_device.tick_all()

            quantum = self._default_quantum
            if self._device_tick_deadline > self._elapsed_cycles:
                if (self._elapsed_cycles + quantum) > self._device_tick_deadline:
                    quantum = self._device_tick_deadline - self._elapsed_cycles

            self.trace('RUN', info=f'quantum {quantum} cycles')
            self._elapsed_cycles += m68k.execute(quantum)

            if self._elapsed_cycles > self._cycle_limit:
                self.fatal('cycle limit exceeded')

    def finish(self):
        elapsed_time = time.time() - self._start_time
        self.trace('END', info='{} cycles in {} seconds, {} cps'.format(self.current_cycle,
                                                                        elapsed_time,
                                                                        int(self.current_cycle / elapsed_time)))
        try:
            self._trace_file.flush()
            self._trace_file.close()
        except Exception:
            pass

    def schedule_device_tick(self, deadline):
        self._device_tick_deadline = deadline
        if (self.current_cycle + m68k.cycles_remaining()) > deadline:
            modify_timeslice(deadline - self.current_cycle)

    def set_quantum(self, new_quantum):
        if (new_quantum > 0) and (new_quantum < self._next_quantum):
            self._next_quantum = new_quantum

    def add_memory(self, base, size, writable=True, contents=None):
        """
        Add RAM/ROM to the emulation
        """
        if not m68k.mem_add_memory(base, size, writable, contents):
            raise RuntimeError(f"failed to add memory 0x{base:x}/{size}")

    def add_device(self, args, dev, address=None, interrupt=None):
        """
        Attach a device to the emulator at the given offset in device space
        """
        if self._root_device is None:
            self._root_device = dev(args=args, emu=self)
            self._root_device.add_system_devices(args)
        else:
            self._root_device.add_device(args=args,
                                         dev=dev,
                                         address=address,
                                         interrupt=interrupt)

    def add_reset_hook(self, hook):
        """
        Add a callback function to be called at reset time
        """
        self._reset_hooks.append(hook)

    @property
    def current_time(self):
        """
        Return the current time in microseconds since reset
        """
        return int(self.current_cycle / self._cpu_frequency * 1000000)

    @property
    def current_cycle(self):
        """
        Return the number of the current clock cycle (cycles elapsed since reset)
        """
        return self._elapsed_cycles + m68k.cycles_run()

    @property
    def cycle_rate(self):
        return self._cpu_frequency

    def trace_enable(self, what, option=None):
        """
        Adjust tracing options
        """
        if what == 'memory':
            self._trace_memory = True
            m68k.mem_set_trace_handler(self.cb_trace_memory)
            m68k.mem_enable_tracing(True)

        elif what == 'instructions':
            self._trace_instructions = True
            m68k.set_instr_hook_callback(self.cb_trace_instruction)
            self.trace_enable('jumps')

        elif what == 'jumps':
            self._trace_jumps = True
            m68k.set_pc_changed_callback(self.cb_trace_jump)

        elif what == 'exceptions':
            m68k.set_pc_changed_callback(self.cb_trace_jump)

        else:
            raise RuntimeError('bad tracing option {}'.format(what))

    def trace(self, action, address=None, info=''):
        """
        Cut a trace entry
        """
        if address is not None:
            symname = self._sym_for_address(address)
            if symname is not None:
                afield = '{} / {:#08x}'.format(symname, address)
            else:
                afield = '{:#08x}'.format(address)
        else:
            afield = ''

        msg = '{:>10}: {:>40} : {}'.format(action, afield, info.strip())

        self._trace_file.write(msg + '\n')

    def log(self, msg):
        print(msg)
        self._trace_file.write(msg + '\n')

    def _sym_for_address(self, address):
        for symfile in self._symbol_files:
            name = symfile.get_symbol_name(address)
            if name is not None:
                return name
        return None

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
            dis = m68k.disassemble(pc, self._cpu_type)
            info = ''
            for reg in self.registers:
                if dis.find(reg) is not -1:
                    info += ' {}={:#x}'.format(reg, m68k.get_reg(self.registers[reg]))

            self.trace('EXECUTE', pc, '{:30} {}'.format(dis, info))
            return

        except Exception:
            self.fatal_exception(sys.exc_info())

    def cb_reset(self):
        """
        Trace reset instructions
        """

        # might want to end here due to memory issues?
        m68k.end_timeslice()

        # call reset hooks
        for hook in self._reset_hooks:
            try:
                hook(self)
            except Exception:
                self.fatal_exception(sys.exc_info())

    def cb_illg(self, instr):
        """
        Illegal instruction handler - implement 'native features' emulator API
        """
        if instr == 0x7300:     # nfID
            self.trace('nFID')
            return self._nfID(m68k.get_reg(self.registers['SP']) + 4)
        elif instr == 0x7301:     # nfCall
            self.trace('nFCall')
            return self._nfCall(m68k.get_reg(self.registers['SP']) + 4)

        # instruction not handled by emulator, legitimately illegal
        return m68k.ILLG_ERROR

    def cb_trace_jump(self, new_pc):
        """
        Cut a jump trace entry, called when the PC changes significantly, usually
        a function call, return or exception
        """
        try:
            self.trace('JUMP', address=new_pc)
        except Exception:
            self.fatal_exception(sys.exc_info())

    def _keyboard_interrupt(self, signal=None, frame=None):
        self.fatal('\rExit due to user interrupt.')

    def _nfID(self, argptr):
        id = self._get_string(argptr)
        if id is None:
            return m68k.ILLG_ERROR

        if id == 'NF_VERSION':
            m68k.set_reg(m68k.REG_D0, 1)
        # elif id == 'NF_NAME':
        #    m68k.set_reg(m68k.REG_D0, 1)
        elif id == 'NF_STDERR':
            m68k.set_reg(m68k.REG_D0, 2)
        elif id == 'NF_SHUTDOWN':
            m68k.set_reg(m68k.REG_D0, 3)
        else:
            return m68k.ILLG_ERROR
        return m68k.ILLG_OK

    def _nfCall(self, argptr):
        func = m68k.mem_read_memory(argptr, m68k.MEM_SIZE_32)
        if func == 0:   # NF_VERSION
            m68k.set_reg(m68k.REG_D0, 1)
        # elif func == 1:
        #    pass
        elif func == 2:
            return self._nf_stderr(argptr + 4)
        elif func == 3:
            self.fatal('shutdown requested')
        else:
            return m68k.ILLG_ERROR
        return m68k.ILLG_OK

    def _nf_stderr(self, argptr):
        msg = self._get_string(argptr)
        if msg is None:
            return m68k.ILLG_ERROR
        sys.stderr.write(msg)
        return m68k.ILLG_OK

    def _get_string(self, argptr):
        strptr = m68k.mem_read_memory(argptr, m68k.MEM_SIZE_32)
        if strptr == 0xffffffff:
            return None
        result = str()
        while True:
            c = m68k.mem_read_memory(strptr, m68k.MEM_SIZE_8)
            if c == 0xffffffff:
                return None
            if (c == 0) or (len(result) > 255):
                return result
            result += chr(c)
            strptr += 1

    def fatal_exception(self, exception_info):
        """
        Call from within a callback handler to register a fatal exception
        """
        self._dead = True
        self._exception_info = exception_info
        m68k.end_timeslice()

    def fatal(self, reason):
        """
        Call from within a callback handler etc. to cause the emulation to exit
        """
        self._dead = True
        self._postmortem = reason
        m68k.end_timeslice()

    def fatal_info(self):
        result = ''
        if self._postmortem is not None:
            result += self._postmortem
        elif self._exception_info is not None:
            etype, value, tb = self._exception_info
            for str in traceback.format_exception(etype, value, tb):
                result += str
        else:
            result += 'no reason'

        return result
