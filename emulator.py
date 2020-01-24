import time
import sys
import signal
import traceback

import device
import imageELF
import imageBIN

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
    M68K_MODE_READ,
    M68K_MODE_WRITE,
    M68K_MODE_FETCH,

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
    mem_add_memory,
    mem_set_trace_handler,
    mem_enable_tracing,
    mem_enable_bus_error,
    mem_read_memory,
    mem_write_memory,
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
        'SSP': M68K_REG_ISP
    }

    cpu_frequency = 8

    def __init__(self, args, cpu="68000"):

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
        self._trace_cycle_limit = 0
        self._check_PC_in_text = False

        self._trace_read_triggers = list()
        self._trace_write_triggers = list()
        self._trace_instruction_triggers = list()
        self._trace_exception_list = list()
        self._trace_jump_cache = dict()

        # 'native features' stderr channel buffer
        self._message_buffer = ''

        # time
        self._elapsed_cycles = 0
        self._device_deadline = 0
        self._quantum = self.cpu_frequency * 1000  # ~1ms

        # reset callbacks
        self._reset_hooks = list()

        # intialise the CPU
        if cpu == "68000":
            self._cpu_type = M68K_CPU_TYPE_68000
        elif cpu == "68010":
            self._cpu_type = M68K_CPU_TYPE_68010
        elif cpu == "68EC020":
            self._cpu_type = M68K_CPU_TYPE_68EC020
        elif cpu == "68020":
            self._cpu_type = M68K_CPU_TYPE_68020
        elif cpu == "68EC030":
            self._cpu_type = M68K_CPU_TYPE_68EC030
        elif cpu == "68030":
            self._cpu_type = M68K_CPU_TYPE_68030
        elif cpu == "68EC040":
            self._cpu_type = M68K_CPU_TYPE_68EC040
        elif cpu == "68LC040":
            self._cpu_type = M68K_CPU_TYPE_68LC040
        elif cpu == "68040":
            self._cpu_type = M68K_CPU_TYPE_68040
        elif cpu == "SCC68070":
            self._cpu_type = M68K_CPU_TYPE_SCC68070
        else:
            raise RuntimeError(f"unsupported CPU: {cpu}")

        set_cpu_type(self._cpu_type)
        cpu_init()

        # attach unconditional callback functions
        set_reset_instr_callback(self.cb_reset)
        set_illg_instr_callback(self.cb_illg)

        # set tracing options
        if args.trace_memory or args.trace_everything:
            self.trace_enable('memory')
        for i in args.trace_read_trigger:
            self.trace_enable('read-trigger', i)
        for i in args.trace_write_trigger:
            self.trace_enable('write-trigger', i)
        if args.trace_instructions or args.trace_everything:
            self.trace_enable('instructions')
        for i in args.trace_instruction_trigger:
            self.trace_enable('instruction-trigger', i)
        if args.trace_jumps or args.trace_everything:
            self.trace_enable('jumps')
        if args.trace_exceptions or args.trace_everything:
            self.trace_enable('exceptions')
        for i in args.trace_exception:
            self.trace_enable('exception', i)
        if args.trace_cycle_limit > 0:
            self.trace_enable('trace-cycle-limit', args.trace_cycle_limit)
        if args.trace_check_PC_in_text or args.trace_everything:
            self.trace_enable('check-pc-in-text')
        if args.cycle_limit > 0:
            self._cycle_limit = args.cycle_limit
        else:
            self._cycle_limit = float('inf')

        # add symbol files
        self._symbol_files = args.symbols

        # XXX load the executable image
        # self._image = self.loadImage(args.image)

    @classmethod
    def add_arguments(cls, parser):

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
        parser.add_argument('--trace-read-trigger',
                            action='append',
                            type=str,
                            default=list(),
                            metavar='ADDRESS-or-NAME',
                            help='enable memory tracing when ADDRESS-or-NAME is read')
        parser.add_argument('--trace-write-trigger',
                            action='append',
                            type=str,
                            default=list(),
                            metavar='ADDRESS-or-NAME',
                            help='enable memory tracing when ADDRESS-or-NAME is written')
        parser.add_argument('--trace-instructions',
                            action='store_true',
                            help='enable instruction tracing at startup (implies --trace-jumps)')
        parser.add_argument('--trace-instruction-trigger',
                            action='append',
                            type=str,
                            default=list(),
                            metavar='ADDRESS-or-NAME',
                            help='enable instruction and jump tracing when execution reaches ADDRESS-or-NAME')
        parser.add_argument('--trace-jumps',
                            action='store_true',
                            help='enable branch tracing at startup')
        parser.add_argument('--trace-exceptions',
                            action='store_true',
                            help='enable tracing all exceptions at startup')
        parser.add_argument('--trace-exception',
                            type=int,
                            action='append',
                            default=list(),
                            metavar='EXCEPTION',
                            help='enable tracing for EXCEPTION at startup (may be specified more than once)')
        parser.add_argument('--trace-io',
                            action='store_true',
                            help='enable tracing of I/O space accesses')
        parser.add_argument('--trace-cycle-limit',
                            type=int,
                            default=0,
                            metavar='CYCLES',
                            help='stop the emulation after CYCLES following an instruction or memory trigger')
        parser.add_argument('--trace-check-PC-in-text',
                            action='store_true',
                            help='when tracing instructions, stop if the PC lands outside the text section')
        parser.add_argument('--symbols',
                            type=str,
                            action='append',
                            metavar='ELF-SYMFILE',
                            help='add ELF objects containing symbols for symbolicating trace')
#        parser.add_argument('image',
#                            type=str,
#                            default='none',
#                            metavar='IMAGE',
#                            help='executable to load')

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
        signal.signal(signal.SIGINT, self._keyboard_interrupt)

        # reset the CPU ready for execution
        pulse_reset()

        self._start_time = time.time()
        while not self._dead:
            cycles_to_run = self._root_device.tick()
            if (cycles_to_run == 0) or (cycles_to_run > self._quantum):
                cycles_to_run = self._quantum
            self._elapsed_cycles += execute(cycles_to_run)

            if mem_is_end():
                self.fatal('illegal memory access')

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
            self._root_device = dev(args=args, emu=self, address=address)
        else:
            self._root_device.add_device(
                args=args, dev=dev, address=address, interrupt=interrupt)

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
        return self.current_cycle / self.cpu_frequency

    @property
    def current_cycle(self):
        """
        Return the number of the current clock cycle (cycles elapsed since reset)
        """
        return self._elapsed_cycles + cycles_run()

    def trace_enable(self, what, option=None):
        """
        Adjust tracing options
        """
        if what == 'memory':
            self._trace_memory = True
            mem_set_trace_func(self.cb_trace_memory)
            mem_set_trace_mode(1)

        elif what == 'read-trigger':
            addrs = self._image.symrange(option)
            self._trace_read_triggers.extend(addrs)
            self.log('adding memory read trigger: {}'.format(option))
            mem_set_trace_func(self.cb_trace_memory)
            mem_set_trace_mode(1)

        elif what == 'write-trigger':
            addrs = self._image.symrange(option)
            self._trace_write_triggers.extend(addrs)
            self.log('adding memory write trigger: {}'.format(option))
            mem_set_trace_func(self.cb_trace_memory)
            mem_set_trace_mode(1)

        elif what == 'instructions':
            self._trace_instructions = True
            set_instr_hook_callback(self.cb_trace_instruction)
            self.trace_enable('jumps')

        elif what == 'instruction-trigger':
            addrs = self._image.symrange(option)
            self._trace_instruction_triggers.append(addrs[0])
            self.log('adding instruction trigger: {}'.format(option))
            set_instr_hook_callback(self.cb_trace_instruction)

        elif what == 'jumps':
            self._trace_jumps = True
            set_pc_changed_callback(self.cb_trace_jump)

        elif what == 'exceptions':
            self._trace_exception_list.extend(range(1, 255))
            set_pc_changed_callback(self.cb_trace_jump)

        elif what == 'exception':
            self._trace_exception_list.append(option)
            set_pc_changed_callback(self.cb_trace_jump)

        elif what == 'trace-cycle-limit':
            self._trace_cycle_limit = option

        elif what == 'check-pc-in-text':
            self._check_PC_in_text = True

        else:
            raise RuntimeError('bad tracing option {}'.format(what))

    def trace(self, action, address=None, info=''):

        if address is not None:
            symname = self._image.symname(address)
            if symname != '':
                afield = '{} / {:#08x}'.format(symname, address)
            else:
                afield = '{:#08x}'.format(address)
        else:
            afield = ''

        msg = '{:>10}: {:>40} : {}'.format(action, afield, info.strip())

        self._trace_file.write(msg + '\n')

    def _trace_trigger(self, address, kind, actions):
        self.trace('TRIGGER', address, '{} trigger'.format(kind))
        for action in actions:
            self.trace_enable(action)
        if self._trace_cycle_limit > 0:
            self._cycle_limit = min(
                self._cycle_limit, self._elapsed_cycles + self._trace_cycle_limit)

    def log(self, msg):
        print(msg)
        self._trace_file.write(msg + '\n')

    def cb_buserror(self, mode, width, addr):
        """
        Handle an invalid memory access
        """
        if mode == M68K_MODE_WRITE:
            cause = 'write to'
        else:
            cause = 'read from'

        self.trace('BUS ERROR', addr, self._image.lineinfo(
            get_reg(M68K_REG_PPC)))
        self.fatal(
            'BUS ERROR during {} 0x{:08x} - invalid memory'.format(cause, addr))

    def cb_trace_memory(self, mode, width, addr, value):
        """
        Cut a memory trace entry
        """
        try:
            # don't trace immediate fetches, since they are described by
            # instruction tracing
            if mode == M68K_MODE_FETCH:
                return 0
            elif mode == M68K_MODE_READ:
                if not self._trace_memory and addr in self._trace_read_triggers:
                    self._trace_trigger(addr, 'memory', ['memory'])
                direction = 'READ'
            elif mode == M68K_MODE_WRITE:
                if not self._trace_memory and addr in self._trace_write_triggers:
                    self._trace_trigger(addr, 'memory', ['memory'])
                direction = 'WRITE'

            if self._trace_memory:
                if width == 0:
                    info = '{:#04x}'.format(value)
                elif width == 1:
                    info = '{:#06x}'.format(value)
                elif width == 2:
                    info = '{:#010x}'.format(value)

                self.trace(direction, addr, info)
        except Exception:
            self.fatal_exception(sys.exc_info())

        return 0

    def cb_trace_instruction(self):
        """
        Cut an instruction trace entry
        """
        try:
            pc = get_reg(M68K_REG_PC)
            if not self._trace_instructions and pc in self._trace_instruction_triggers:
                self._trace_trigger(pc, 'instruction', [
                                    'instructions', 'jumps'])

            if self._trace_instructions:
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
        # might want to end here due to memory issues
        end_timeslice()

        # call reset hooks
        for hook in self._reset_hooks:
            try:
                hook(self)
            except Exception:
                self.fatal_exception(sys.exc_info())

    def cb_illg(self):
        """
        Illegal instruction handler - implement 'native features' emulator API
        """
        # instruction not handled by emulator
        return 1

    def cb_trace_jump(self, new_pc, vector):
        """
        Cut a jump trace entry, called when the PC changes significantly, usually
        a function call, return or exception
        """
        try:
            if vector == 0:
                if self._trace_jumps:
                    self.trace('JUMP', new_pc, self._image.lineinfo(new_pc))
            else:
                if vector in self._trace_exception_list:
                    ppc = get_reg(M68K_REG_PPC)
                    self.trace('EXCEPTION', ppc, 'vector {:#x} to {}'.format(
                        vector, self._image.lineinfo(new_pc)))
        except Exception:
            self.fatal_exception(sys.exc_info())

    def _keyboard_interrupt(self, signal=None, frame=None):
        now = time.time()
        interval = now - self._first_interrupt_time

        if interval >= 1.0:
            self._first_interrupt_time = now
            self._interrupt_count = 1
        else:
            self._interrupt_count += 1
            if self._interrupt_count >= 3:
                self.fatal('Exit due to user interrupt.')

        self._root_device.console_input(3)

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
