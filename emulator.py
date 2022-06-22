#
# Core emulator logic
#

import signal
import sys
import time
import traceback

from device import Device
from imageELF import ELFImage
from musashi import m68k
from systemdevices import RootDevice
from trace import Trace


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

    nf_map = {
        1: 'NF_VERSION',
        2: 'NF_STDERR',
        3: 'NF_SHUTDOWN',
        4: 'NF_CTRL',
        5: 'NF_DISKIO'
    }

    nf_ctl_ops = {
        1: 'TRACE_STOP',             # immediate stop
        2: 'TRACE_START',            # arg = number of cycles to trace
        3: 'RUN_CYCLES',             # arg = number of cycles before shutdown
    }

    def __init__(self, args, cpu="68000", frequency=8000000):

        self._dead = False
        self._exception_info = None
        self._postmortem = None

        self._trace = Trace(args, emulator=self)

        # time
        self._cpu_frequency = frequency
        self._elapsed_cycles = 0
        self._device_deadline = 0
        self._default_quantum = int(self._cpu_frequency / 1000)  # ~1ms in cycles
        self._device_callback_at = sys.maxsize
        self._device_callback_fn = None

        # intialise the CPU
        try:
            self._cpu_type = self.cpu_map[cpu]
        except KeyError:
            raise RuntimeError(f"unsupported CPU: {cpu}")
        m68k.set_cpu_type(self._cpu_type)
        m68k.cpu_init()

        # attach unconditional callback functions
        self._reset_hooks = list()
        m68k.set_reset_instr_callback(self.cb_reset)
        m68k.set_illg_instr_callback(self.cb_illg)

        # load an executable?
        if args.load is not None:
            self._load_image = ELFImage(args.load)
            self._load_address = args.load_address
            self._trace.add_symbol_image(self._load_image)
        else:
            self._load_image = None

        # decide how long to run for
        if args.cycle_limit > 0:
            self._cycle_limit = args.cycle_limit
        else:
            self._cycle_limit = sys.maxsize
        self._trace_cycle_limit = sys.maxsize

        if not args.disable_bus_error:
            m68k.mem_enable_bus_error(True)

        # wire up the root device
        self.add_device(args, RootDevice, emulator=self)

        # hook up the NF disk file (if supplie)
        if args.nf_diskfile is not None:
            self._nf_diskfile = open(args.nf_diskfile, "wb")
            self._nf_diskfile.seek(0, SEEK_END)
            self._nf_diskfile_size = self._nf_diskfile.tell()
        else:
            self._nf_diskfile = None

    @classmethod
    def add_arguments(cls, parser, default_load_address=0x400):

        parser.add_argument('--cycle-limit',
                            type=int,
                            default=float('inf'),
                            metavar='CYCLES',
                            help='stop the emulation after CYCLES machine cycles')
        parser.add_argument('--load',
                            type=str,
                            metavar='ELF-PROGRAM',
                            help='load an ELF program (may require ROM load to be disabled)')
        parser.add_argument('--load-address',
                            type=int,
                            metavar='LOAD-ADDRESS',
                            default=default_load_address,
                            help='relocate loaded ELF programs to this address before running')
        parser.add_argument('--disable-bus-error',
                            action='store_true',
                            default=False,
                            help='disable generation of bus error on any bad memory access')
        parser.add_argument('--nf-diskfile',
                            type=str,
                            metavar='DISK-FILE',
                            help='open DISK-FILE and make it available to the emulated program via the Native Features API')

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

        # reset the CPU ready for execution
        m68k.pulse_reset()

        # reset everything
        self.cb_reset()

        self._start_time = time.time()
        while not self._dead:

            quantum = self._default_quantum
            if (self._elapsed_cycles + quantum) > self._device_callback_at:
                quantum = self._device_callback_at - self._elapsed_cycles
            if (self._elapsed_cycles + quantum) > self._cycle_limit:
                quantum = self._cycle_limit - self._elapsed_cycles
            if (self._elapsed_cycles + quantum) > self._trace_cycle_limit:
                quantum = self._trace_cycle_limit - self._elapsed_cycles

            self.trace(action='RUN', info=f'quantum {quantum} cycles @ {self._elapsed_cycles}')
            run_count = m68k.execute(quantum)
            self.trace(action='STOP', info=f'ran for {run_count} cycles')
            self._elapsed_cycles += run_count

            if self._elapsed_cycles >= self._cycle_limit:
                self.fatal('cycle limit exceeded')
            if self._elapsed_cycles >= self._trace_cycle_limit:
                self._trace.enable('everything', False)
            if self._elapsed_cycles >= self._device_callback_at:
                self._device_callback_at = sys.maxsize
                self._device_callback_fn()

    def finish(self):
        elapsed_time = time.time() - self._start_time
        self.trace(action='END',
                   info=f'{self.current_cycle} cycles in {elapsed_time} seconds, {int(self.current_cycle / elapsed_time)} cps')
        self._trace.close()

    def set_device_callback(self, device_callback_at, device_callback_fn):
        if device_callback_at <= self.current_cycle:
            raise RuntimeError(f'device attempted to set callback in the past')

        self._device_callback_at = device_callback_at
        callback_after = device_callback_at - self.current_cycle
        if callback_after < m68k.cycles_remaining():
            m68k.modify_timeslice(callback_after)
        self._device_callback_fn = device_callback_fn

    def add_memory(self, base, size, writable=True, from_file=None):
        """
        Add RAM/ROM to the emulation
        """
        if not m68k.mem_add_memory(base, size, writable):
            raise RuntimeError(f"failed to add memory 0x{base:x}/{size}")

        if from_file is not None:
            mem_image = open(from_file, "rb").read(size + 1)
            if (len(mem_image) > size):
                raise RuntimeError(f"Memory image image {from_file} must be <= {size:#x}")
            print(f'loaded {len(mem_image)} bytes at {base:#x}')
            m68k.mem_write_bulk(base, mem_image)

    def remove_memory(self, base):
        """
        Remove RAM/ROM from the emulation
        """
        if not m68k.mem_remove_memory(base):
            raise RuntimeError(f"failed to remove memory 0x{base:x}/{size}")

    def add_device(self, args, dev, **options):
        """
        Attach a device to the emulator
        """
        Device.add_device(args, dev, **options)

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

    def cb_reset(self):
        """
        Trace reset instructions
        """

        # might want to end here due to memory issues?
        m68k.end_timeslice()

        # call reset hooks
        for hook in self._reset_hooks:
            try:
                hook()
            except Exception:
                self.fatal_exception(sys.exc_info())

    def cb_illg(self, instr):
        """
        Illegal instruction handler - implement 'native features' emulator API
        """
        if instr == 0x7300:     # nfID
            return self._nfID(m68k.get_reg(m68k.REG_SP) + 4)
        elif instr == 0x7301:     # nfCall
            return self._nfCall(m68k.get_reg(m68k.REG_SP) + 4)

        # instruction not handled by emulator, legitimately illegal
        return m68k.ILLG_ERROR

    def _keyboard_interrupt(self, signal=None, frame=None):
        self.fatal('\rExit due to user interrupt.')

    def _nfID(self, argptr):
        name = self._get_string(argptr)
        if name is None:
            return m68k.ILLG_ERROR

        for func_code, func_name in self.nf_map.items():
            if name == func_name:
                m68k.set_reg(m68k.REG_D0, func_code)
                return m68k.ILLG_OK
        return m68k.ILLG_ERROR

    def _nfCall(self, argptr):
        func_code = m68k.mem_read_memory(argptr, m68k.MEM_SIZE_32)
        try:
            func_name = self.nf_map[func_code]
        except KeyEror:
            return m68k.ILLG_ERROR

        if func_name == 'NF_VERSION':
            m68k.set_reg(m68k.REG_D0, 1)
        elif func_name == 'NF_STDERR':
            self._nf_stderr(argptr + 4)
        elif func_name == 'NF_SHUTDOWN':
            self.fatal('shutdown requested')
        elif func_name == 'NF_CTRL':
            self._nf_trace(argptr + 4)
        elif func_name == 'NF_DISKIO':
            m68k.set_reg(m68k.REG_D0, 0 if self._nf_diskio(argptr + 4) else 1)
        else:
            return m68k.ILLG_ERROR
        return m68k.ILLG_OK

    def _nf_stderr(self, argptr):
        msg = self._get_string(argptr)
        if msg is None:
            return m68k.ILLG_ERROR
        sys.stderr.write(msg)
        return m68k.ILLG_OK

    def _nf_ctl(self, argptr):
        cmd = m68k_read_memory(argptr, m68k.MEM_SIZE_32)
        arg = m68k_read_memory(argptr + 4, m68k.MEM_SIZE_32)

        try:
            op = self.nf_ctl_ops[cmd]
        except KeyError:
            return m68k.ILLG_ERROR

        if op == 'TRACE_STOP':
            self._trace.enable('everything', False)
        elif op == 'TRACE_START':
            self._trace.enable('everything', True)
            if arg == 0:
                self._trace_cycle_limit = sys.maxsize
            else:
                self._trace_cycle_limit = self.current_cycle + arg
                m68k.end_timeslice()
        elif op == 'RUN_CYCLES':
            if arg == 0:
                self._cycle_limit = sys.maxsize
            else:
                self._cycle_limit = self.current_cycle + arg
                m68k.end_timeslice()
        else:
            return m68k.ILLG_ERROR
        return m68k.ILLG_OK

    def _nf_diskio(self, argptr):
        cmd = m68k_read_memory(argptr, m68k.MEM_SIZE_32)
        byteoff = m68k_read_memory(argptr + 4, m68k.MEM_SIZE_32) * 512
        buf = m68k_read_memory(argptr + 8, m68k.MEM_SIZE_32)

        if self._nf_diskfile is None:
            return False
        if byteoff >= self._nf_diskfile_size:
            return False
        if cmd == 1:
            self._nf_diskfile.seek(byteoff)
            blk = self._nf_diskfile.read(512)
            if (len(blk) == 512):
                m68k.mem_write_bulk(buf, blk)
                return True
        elif cmd == 2:
            blk = bytes()
            while len(blk) < 512:
                blk.append(m68k.mem_read_memory(buf, m68k.MEM_SIZE_32))
                buf += 4
            self._nf_diskfile.seek(byteoff)
            self._nf_diskfile.write(blk)
            return True
        return False

    def _get_string(self, argptr):
        strptr = m68k.mem_read_memory(argptr, m68k.MEM_SIZE_32)
        if strptr == 0:
            return None
        result = str()
        while True:
            c = m68k.mem_read_memory(strptr, m68k.MEM_SIZE_8)
            if (c == 0) or (len(result) > 255):
                return result
            result += chr(c)
            strptr += 1

    def trace(self, action='', address=None, info=''):
        self._trace.trace(action=action, address=address, info=info)

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
