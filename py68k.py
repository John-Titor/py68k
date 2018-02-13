#!/usr/bin/python
#
# A M68K emulator for development purposes
#

import os
import argparse
import subprocess
import time
import curses
import sys
import signal
import traceback

import device
import imageELF
import imageBIN

from musashi.m68k import (
    cpu_init,
    disassemble,
    cycles_run,
    end_timeslice,
    execute,
    get_reg,
    mem_init,
    mem_is_end,
    mem_ram_write_block,
    mem_set_invalid_func,
    mem_set_trace_func,
    mem_set_trace_mode,
    pulse_reset,
    set_cpu_type,
    set_instr_hook_callback,
    set_pc_changed_callback,
    set_reset_instr_callback,
    M68K_CPU_TYPE_68000,
    M68K_CPU_TYPE_68010,
    M68K_CPU_TYPE_68020,
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
    M68K_MODE_FETCH
)


class emulator(object):

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

    def __init__(self, args, memory_size):

        self._dead = False
        self._exception_info = None
        self._postmortem = None
        self._first_interrupt_time = 0.0
        self._interrupt_count = 0
        self._root_device = None

        # initialise tracing
        self._trace_file = open(args.trace_file, "w")
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

        # allocate memory for the emulation
        mem_init(memory_size)

        # time
        self._elapsed_cycles = 0
        self._device_deadline = 0
        self._quantum = self.cpu_frequency * 1000  # ~1ms

        # intialise the CPU
        self._cpu_type = M68K_CPU_TYPE_68000
        set_cpu_type(self._cpu_type)
        cpu_init()

        # attach unconditional callback functions
        set_reset_instr_callback(self.cb_trace_reset)
        mem_set_invalid_func(self.cb_buserror)

        # enable memory tracing
        mem_set_trace_mode(1)

        # load the executable image
        self._image = self.loadImage(args.image)

    def loadImage(self, image_filename):
        try:
            suffix = image_filename.split('.')[1]
        except:
            raise RuntimeError("image filename must have an extension")

        if suffix == "elf":
            image = imageELF.image(self, image_filename)
        elif suffix == "bin":
            image = imageBIN.image(self, image_filename)
        else:
            raise RuntimeError("image filename must end in .elf or .bin")

        return image

    def run(self, cycle_limit=float('inf')):
        signal.signal(signal.SIGINT, self._keyboard_interrupt)

        # reset the CPU ready for execution
        pulse_reset()

        self._start_time = time.time()
        self._cycle_limit = cycle_limit
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

    def add_device(self, args, dev, address=None, interrupt=None):
        """
        Attach a device to the emulator at the given offset in device space
        """
        if self._root_device is None:
            self._root_device = dev(args=args, emu=self, address=address)
        else:
            self._root_device.add_device(
                args=args, dev=dev, address=address, interrupt=interrupt)

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

        elif what == 'read-trigger':
            addrs = self._image.symrange(option)
            self._trace_read_triggers.extend(addrs)
            self.log('adding memory read trigger: {}'.format(option))
            mem_set_trace_func(self.cb_trace_memory)

        elif what == 'write-trigger':
            addrs = self._image.symrange(option)
            self._trace_write_triggers.extend(addrs)
            self.log('adding memory write trigger: {}'.format(option))
            mem_set_trace_func(self.cb_trace_memory)

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
        print msg
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
        except:
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
        except:
            self.fatal_exception(sys.exc_info())

    def cb_trace_reset(self):
        """
        Trace reset instructions
        """
        # might want to end here due to memory issues
        end_timeslice()

        # devices must reset
        try:
            self._root_device.reset()
        except:
            self.fatal_exception(sys.exc_info())

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
        except:
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


def configure(args, stdscr):
    if args.target == 'simple':
        emu = emulator(args, memory_size=128)

        # add some devices
        emu.add_device(args, device.root_device, 0xff0000)
        emu.add_device(args, device.uart, 0xff0000, M68K_IRQ_2)
        emu.add_device(args, device.timer, 0xff1000, M68K_IRQ_6)

    elif args.target == 'tiny68k':
        emu = emulator(args, memory_size=(16 * 1024 - 32))

        emu.add_device(args, device.root_device, 0xff8000)

        import deviceDUART
        emu.add_device(args,
                       deviceDUART.DUART,
                       address=0xfff000,
                       interrupt=M68K_IRQ_2)

        import deviceCF
        emu.add_device(args,
                       deviceCF.CompactFlash,
                       address=0xffe000)

    else:
        raise RuntimeError('unsupported target: ' + args.target)

    import deviceConsole
    deviceConsole.Console.stdscr = stdscr
    emu.add_device(args, deviceConsole.Console)

    return emu


def run_emu(stdscr, args):
    # get an emulator
    emu = configure(args, stdscr)

    # set tracing options
    if args.trace_memory or args.trace_everything:
        emu.trace_enable('memory')
    for i in args.trace_read_trigger:
        emu.trace_enable('read-trigger', i)
    for i in args.trace_write_trigger:
        emu.trace_enable('write-trigger', i)
    if args.trace_instructions or args.trace_everything:
        emu.trace_enable('instructions')
    for i in args.trace_instruction_trigger:
        emu.trace_enable('instruction-trigger', i)
    if args.trace_jumps or args.trace_everything:
        emu.trace_enable('jumps')
    if args.trace_exceptions or args.trace_everything:
        emu.trace_enable('exceptions')
    for i in args.trace_exception:
        emu.trace_enable('exception', i)
    if args.trace_cycle_limit > 0:
        emu.trace_enable('trace-cycle-limit', args.trace_cycle_limit)
    if args.trace_check_PC_in_text or args.trace_everything:
        emu.trace_enable('check-pc-in-text')

    # run some instructions
    emu.run(args.cycle_limit)

    emu.finish()
    return emu.fatal_info()


# Parse commandline arguments
parser = argparse.ArgumentParser(description='m68k emulator')

parser.add_argument('--target',
                    type=str,
                    default='none',
                    help='target machine, one of simple, tiny68k')
parser.add_argument('--trace-file',
                    type=str,
                    default='trace.out',
                    help='trace output file')
parser.add_argument('--cycle-limit',
                    type=long,
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
parser.add_argument('--debug-device',
                    type=str,
                    default='',
                    help='comma-separated list of devices to enable debug tracing, \'device\' to trace device framework')
parser.add_argument('--diskfile',
                    type=str,
                    default=None,
                    help='disk image file')
parser.add_argument('image',
                    type=str,
                    default='none',
                    help='executable to load')
args = parser.parse_args()

print curses.wrapper(run_emu, args)
