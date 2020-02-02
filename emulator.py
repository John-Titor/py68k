import time
import sys
import signal
import traceback

from imageELF import ELFImage
# import imageBIN

from device import RootDevice

from musashi.m68k import (

    # Musashi API
    M68K_CPU_TYPE_INVALID,
    M68K_CPU_TYPE_68000,
    M68K_CPU_TYPE_68010,
    M68K_CPU_TYPE_68EC020,
    M68K_CPU_TYPE_68020,
    M68K_CPU_TYPE_68EC030,
    M68K_CPU_TYPE_68030,
    M68K_CPU_TYPE_68EC040,
    M68K_CPU_TYPE_68LC040,
    M68K_CPU_TYPE_68040,
    M68K_CPU_TYPE_SCC68070,
    M68K_IRQ_1,
    M68K_IRQ_2,
    M68K_IRQ_3,
    M68K_IRQ_4,
    M68K_IRQ_5,
    M68K_IRQ_6,
    M68K_IRQ_7,
    M68K_REG_D0,
    M68K_REG_D1,
    M68K_REG_D2,
    M68K_REG_D3,
    M68K_REG_D4,
    M68K_REG_D5,
    M68K_REG_D6,
    M68K_REG_D7,
    M68K_REG_A0,
    M68K_REG_A1,
    M68K_REG_A2,
    M68K_REG_A3,
    M68K_REG_A4,
    M68K_REG_A5,
    M68K_REG_A6,
    M68K_REG_A7,
    M68K_REG_PC,
    M68K_REG_PPC,
    M68K_REG_SR,
    M68K_REG_SP,
    M68K_REG_USP,
    M68K_REG_ISP,

    cpu_init,
    disassemble,
    cycles_run,
    end_timeslice,
    execute,
    get_reg,
    set_reg,
    pulse_reset,
    set_cpu_type,
    set_instr_hook_callback,
    set_pc_changed_callback,
    set_reset_instr_callback,
    set_illg_instr_callback,

    # Memory API
    MEM_READ,
    MEM_WRITE,
    INVALID_READ,
    INVALID_WRITE,
    MEM_MAP,
    MEM_WIDTH_8,
    MEM_WIDTH_16,
    MEM_WIDTH_32,
    MEM_MAP_ROM,
    MEM_MAP_RAM,
    MEM_MAP_DEVICE,

    mem_add_memory,
    mem_set_trace_handler,
    mem_enable_tracing,
    mem_enable_bus_error,
    mem_read_memory,
    mem_write_memory,
    mem_write_bulk,
)


class Emulator(object):

    registers = {
        'D0': M68K_REG_D0,
        'D1': M68K_REG_D1,
        'D2': M68K_REG_D2,
        'D3': M68K_REG_D3,
        'D4': M68K_REG_D4,
        'D5': M68K_REG_D5,
        'D6': M68K_REG_D6,
        'D7': M68K_REG_D7,
        'A0': M68K_REG_A0,
        'A1': M68K_REG_A1,
        'A2': M68K_REG_A2,
        'A3': M68K_REG_A3,
        'A4': M68K_REG_A4,
        'A5': M68K_REG_A5,
        'A6': M68K_REG_A6,
        'A7': M68K_REG_A7,
        'PC': M68K_REG_PC,
        'SR': M68K_REG_SR,
        'SP': M68K_REG_SP,
        'USP': M68K_REG_USP,
        'SSP': M68K_REG_ISP,
    }

    cpu_map = {
        '68000': M68K_CPU_TYPE_68000,
        '68010': M68K_CPU_TYPE_68010,
        '68EC020': M68K_CPU_TYPE_68EC020,
        '68020': M68K_CPU_TYPE_68020,
        '68EC030': M68K_CPU_TYPE_68EC030,
        '68030': M68K_CPU_TYPE_68030,
        '68EC040': M68K_CPU_TYPE_68EC040,
        '68LC040': M68K_CPU_TYPE_68LC040,
        '68040': M68K_CPU_TYPE_68040,
        'SCC68070': M68K_CPU_TYPE_SCC68070,
    }

    operation_map = {
        MEM_READ: 'READ',
        MEM_WRITE: 'WRITE',
        INVALID_READ: 'BAD_READ',
        INVALID_WRITE: 'BAD_WRITE',
        MEM_MAP: 'MAP'
    }

    def __init__(self, args, cpu="68000", frequency=8000000):

        self._dead = False
        self._exception_info = None
        self._postmortem = None
        self._first_interrupt_time = 0.0
        self._interrupt_count = 0
        self._root_device = None

        # initialise tracing
        self._trace_file = open(args.trace_file, "w", 1)
        self._trace_memory = False
        self._trace_instructions = False
        self._trace_jumps = False

        # files and symbolication
        self._load_image = None
        self._symbol_files = list()

        # 'native features' stderr channel buffer
        self._message_buffer = ''

        # time
        self._cpu_frequency = frequency
        self._elapsed_cycles = 0
        self._device_deadline = 0
        self._quantum = int(self._cpu_frequency / 1000)  # ~1ms in cycles

        # reset callbacks
        self._reset_hooks = list()

        # intialise the CPU
        try:
            self._cpu_type = self.cpu_map[cpu]
        except KeyError:
            raise RuntimeError(f"unsupported CPU: {cpu}")

        set_cpu_type(self._cpu_type)
        cpu_init()

        # attach unconditional callback functions
        set_reset_instr_callback(self.cb_reset)
        set_illg_instr_callback(self.cb_illg)

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
                mem_write_bulk(section_address, section_data)

            # patch the initial stack and entrypoint
            _, stack_limit = self._load_image.get_symbol_range('__STACK__')
            if stack_limit is not None:
                mem_write_memory(0x0, MEM_WIDTH_32, stack_limit)
            mem_write_memory(0x4, MEM_WIDTH_32, self._load_image.entrypoint)

        signal.signal(signal.SIGINT, self._keyboard_interrupt)
        print('\nHit ^C to exit\n')

        # reset everything
        self.cb_reset()

        # reset the CPU ready for execution
        pulse_reset()

        self._start_time = time.time()
        while not self._dead:
            cycles_to_run = self._root_device.tick()
            if (cycles_to_run is None) or (cycles_to_run > self._quantum):
                cycles_to_run = self._quantum
            self._elapsed_cycles += execute(cycles_to_run)

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

    def add_memory(self, base, size, writable=True, contents=None):
        """
        Add RAM/ROM to the emulation
        """
        if not mem_add_memory(base, size, writable, contents):
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
        return int(self.current_cycle / self._cpu_frequency)

    @property
    def current_cycle(self):
        """
        Return the number of the current clock cycle (cycles elapsed since reset)
        """
        return self._elapsed_cycles + cycles_run()

    @property
    def cycle_rate(self):
        return self._cpu_frequency

    def trace_enable(self, what, option=None):
        """
        Adjust tracing options
        """
        if what == 'memory':
            self._trace_memory = True
            mem_set_trace_handler(self.cb_trace_memory)
            mem_enable_tracing(True)

        elif what == 'instructions':
            self._trace_instructions = True
            set_instr_hook_callback(self.cb_trace_instruction)
            self.trace_enable('jumps')

        elif what == 'jumps':
            self._trace_jumps = True
            set_pc_changed_callback(self.cb_trace_jump)

        elif what == 'exceptions':
            set_pc_changed_callback(self.cb_trace_jump)

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
            if operation == MEM_MAP:
                if value == MEM_MAP_RAM:
                    info = f'RAM {size:#x}'
                elif value == MEM_MAP_ROM:
                    info = f'ROM {size:#x}'
                elif value == MEM_MAP_DEVICE:
                    info = f'DEVICE {size:#x}'
                else:
                    raise RuntimeError(f'unexpected mapping type {value}')
            else:
                if size == MEM_WIDTH_8:
                    info = f'{value:#04x}'
                elif size == MEM_WIDTH_16:
                    info = f'{value:#06x}'
                elif size == MEM_WIDTH_32:
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
            dis = disassemble(pc, self._cpu_type)
            info = ''
            for reg in self.registers:
                if dis.find(reg) is not -1:
                    info += ' {}={:#x}'.format(reg,
                                               get_reg(self.registers[reg]))

            self.trace('EXECUTE', pc, '{:30} {}'.format(dis, info))
            return

        except Exception:
            self.fatal_exception(sys.exc_info())

    def cb_reset(self):
        """
        Trace reset instructions
        """

        # might want to end here due to memory issues?
        end_timeslice()

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
        # instruction not handled by emulator, legitimately illegal
        return 0

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

    def fatal_exception(self, exception_info):
        """
        Call from within a callback handler to register a fatal exception
        """
        self._dead = True
        self._exception_info = exception_info
        end_timeslice()

    def fatal(self, reason):
        """
        Call from within a callback handler etc. to cause the emulation to exit
        """
        self._dead = True
        self._postmortem = reason
        end_timeslice()

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
