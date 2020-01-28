#!/usr/bin/env python
#
# m68k.py
#
# wrapper for musashi m68k CPU emulator
#

import os
from ctypes import *

# --- Constants ---

# cpu type
M68K_CPU_TYPE_INVALID = 0
M68K_CPU_TYPE_68000 = 1
M68K_CPU_TYPE_68010 = 2
M68K_CPU_TYPE_68EC020 = 3
M68K_CPU_TYPE_68020 = 4
M68K_CPU_TYPE_68EC030 = 5
M68K_CPU_TYPE_68030 = 6
M68K_CPU_TYPE_68EC040 = 7
M68K_CPU_TYPE_68LC040 = 8
M68K_CPU_TYPE_68040 = 9
M68K_CPU_TYPE_SCC68070 = 0


# registers
M68K_REG_D0 = 0
M68K_REG_D1 = 1
M68K_REG_D2 = 2
M68K_REG_D3 = 3
M68K_REG_D4 = 4
M68K_REG_D5 = 5
M68K_REG_D6 = 6
M68K_REG_D7 = 7
M68K_REG_A0 = 8
M68K_REG_A1 = 9
M68K_REG_A2 = 10
M68K_REG_A3 = 11
M68K_REG_A4 = 12
M68K_REG_A5 = 13
M68K_REG_A6 = 14
M68K_REG_A7 = 15
M68K_REG_PC = 16  # Program Counter
M68K_REG_SR = 17  # Status Register
M68K_REG_SP = 18  # The current Stack Pointer (located in A7)
M68K_REG_USP = 19  # User Stack Pointer
M68K_REG_ISP = 20  # Interrupt Stack Pointer
M68K_REG_MSP = 21  # Master Stack Pointer
M68K_REG_SFC = 22  # Source Function Code
M68K_REG_DFC = 23  # Destination Function Code
M68K_REG_VBR = 24  # Vector Base Register
M68K_REG_CACR = 25  # Cache Control Register
M68K_REG_CAAR = 26  # Cache Address Register

M68K_REG_PREF_ADDR = 27  # Virtual Reg: Last prefetch address
M68K_REG_PREF_DATA = 28  # Virtual Reg: Last prefetch data

M68K_REG_PPC = 29  # Previous value in the program counter
M68K_REG_IR = 30  # Instruction register
M68K_REG_CPU_TYPE = 31  # Type of CPU being run

# interrupts
M68K_IRQ_AUTOVECTOR = 0xffffffff
M68K_IRQ_SPURIOUS = 0xfffffffe
M68K_IRQ_NONE = 0
M68K_IRQ_1 = 1
M68K_IRQ_2 = 2
M68K_IRQ_3 = 3
M68K_IRQ_4 = 4
M68K_IRQ_5 = 5
M68K_IRQ_6 = 6
M68K_IRQ_7 = 7

MEM_PAGE_SIZE = 4096
MEM_PAGE_MASK = MEM_PAGE_SIZE - 1
MEM_READ = 0
MEM_WRITE = 1
DEV_READ = 2
DEV_WRITE = 3
INVALID_READ = 4
INVALID_WRITE = 5
MEM_WIDTH_8 = 0
MEM_WIDTH_16 = 1
MEM_WIDTH_32 = 2


def find_lib():
    """ locate the Mushashi dylib """
    path = os.path.dirname(os.path.realpath(__file__))
    all_files = os.listdir(path)
    for f in all_files:
        if f.find('libmusashi') != -1:
            return os.path.join(path, f)
    raise ImportError("Can't find musashi native lib")


lib_file = find_lib()
lib = CDLL(lib_file)

# Musashi API

int_ack_callback_func_type = CFUNCTYPE(c_int, c_int)
bkpt_ack_callback_func_type = CFUNCTYPE(None, c_uint)
reset_instr_callback_func_type = CFUNCTYPE(None)
pc_changed_callback_func_type = CFUNCTYPE(None, c_uint)
tas_instr_callback_func_type = CFUNCTYPE(c_int)
illg_instr_callback_func_type = CFUNCTYPE(c_int, c_int)
fc_callback_func_type = CFUNCTYPE(None, c_uint)
instr_hook_callback_func_type = CFUNCTYPE(None, c_uint)


def set_int_ack_callback(func):
    global int_ack_callback
    int_ack_callback = int_ack_callback_func_type(func)
    lib.m68k_set_int_ack_callback(int_ack_callback)


def set_bkpt_ack_callback(func):
    global bkpt_ack_callback
    bkpt_ack_callback = bkpt_ack_callback_func_type(func)
    lib.m68k_set_bkpt_ack_callback(bkpt_ack_callback)


def set_reset_instr_callback(func):
    global reset_instr_callback
    reset_instr_callback = reset_instr_callback_func_type(func)
    lib.m68k_set_reset_instr_callback(reset_instr_callback)


def set_pc_changed_callback(func):
    global pc_changed_callback
    pc_changed_callback = pc_changed_callback_func_type(func)
    lib.m68k_set_pc_changed_callback(pc_changed_callback)


def set_tas_instr_callback(func):
    global tas_instr_callback
    tas_instr_callback = tas_instr_callback_func_type(func)
    lib.m68k_set_tas_instr_callback(tas_instr_callback)


def set_illg_instr_callback(func):
    global illg_instr_callback
    illg_instr_callback = illg_instr_callback_func_type(func)
    lib.m68k_set_illg_instr_callback(illg_instr_callback)


def set_fc_callback(func):
    global fc_callback
    fc_callback = fc_callback_func_type(func)
    lib.m68k_set_fc_callback(fc_callback)


def set_instr_hook_callback(func):
    global instr_hook_callback
    instr_hook_callback = instr_hook_callback_func_type(func)
    lib.m68k_set_instr_hook_callback(instr_hook_callback)


lib.m68k_get_virq.restype = c_uint
lib.m68k_get_reg.restype = c_uint
lib.m68k_is_valid_instruction.restype = c_uint
lib.m68k_disassemble.restype = c_uint
__dis_buf = create_string_buffer(100)


def set_cpu_type(cpu_type):
    lib.m68k_set_cpu_type(c_uint(cpu_type))


def cpu_init():
    lib.m68k_init()


def pulse_reset():
    lib.m68k_pulse_reset()


def execute(cycles):
    return lib.m68k_execute(c_int(cycles))


def cycles_run():
    return lib.m68k_cycles_run()


def cycles_remaining():
    return lib.m68k_cycles_remaining_func()


def modify_timeslice(cycles):
    lib.m68k_modify_timeslice(c_int(cycles))


def end_timeslice():
    lib.m68k_end_timeslice()


def set_irq(level):
    lib.m68k_set_irq(c_uint(level))


def set_virq(level, active):
    lib.m68k_set_virq(c_uint(level), c_uint(active))


def get_virq(level):
    lib.m68k_get_virq(c_uint(level))


def pulse_halt():
    lib.m68k_pulse_halt()


def pulse_bus_error():
    lib.m68k_pulse_bus_error()


"""
/* Get the size of the cpu context in bytes */
unsigned int m68k_context_size(void);

/* Get a cpu context */
unsigned int m68k_get_context(void* dst);

/* set the current cpu context */
void m68k_set_context(void* dst);

/* Register the CPU state information */
void m68k_state_register(const char *type, int index);
"""


def get_reg(reg):
    return lib.m68k_get_reg(None, c_int(reg))


def set_reg(reg, value):
    lib.m68k_set_reg(c_int(reg), c_uint(value))


def is_valid_instruction(instr, cpu_type):
    return lib.m68k_is_valid_instruction(c_uint(instr),
                                         c_uint(cpu_type))


def disassemble(pc, cpu_type):
    n = lib.m68k_disassemble(c_char_p(__dis_buf),
                             c_uint(pc),
                             c_uint(cpu_type))
    return __dis_buf.value.decode('ascii')


"""
unsigned int m68k_disassemble_raw(char* str_buff, unsigned int pc, const unsigned char* opdata, const unsigned char* argdata, unsigned int cpu_type);
"""

# Memory API

lib.mem_add_memory.restype = c_bool
lib.mem_add_device.restype = c_bool
lib.mem_read_memory.restype = c_uint
device_handler_func_type = CFUNCTYPE(c_uint, c_int, c_uint, c_uint, c_ubyte, c_uint)
trace_handler_func_type = CFUNCTYPE(None, c_int, c_uint, c_ubyte, c_uint)


def mem_add_memory(base, size, writable=True, with_bytes=None):
    return lib.mem_add_memory(c_uint(base),
                              c_uint(size),
                              c_bool(writable),
                              c_char_p(with_bytes))


def mem_add_device(base, size, handle):
    return lib.mem_add_device(c_uint(base),
                              c_uint(size),
                              c_uint(handle))


def mem_set_device_handler(func):
    global device_handler
    device_handler = device_handler_func_type(func)
    lib.mem_set_device_handler(device_handler)


def mem_set_trace_handler(func):
    global trace_handler
    trace_handler = trace_handler_func_type(func)
    lib.mem_set_trace_handler(trace_handler)


def mem_enable_tracing(enable=True):
    lib.mem_enable_tracing(c_bool(enable))


def mem_enable_bus_error(enable=True):
    lib.mem_enable_bus_error(c_bool(enable))


def mem_read_memory(address, width):
    return lib.mem_read_memory(c_uint(address), c_ubyte(width))


def mem_write_memory(address, width, value):
    lib.mem_write_memory(c_uint(address), c_ubyte(width), c_uint(value))


def mem_write_bulk(address, bytes):
    lib.mem_write_bulk(c_uint(address), bytes, c_uint(len(bytes)))
