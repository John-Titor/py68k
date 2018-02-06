#!/usr/bin/env python
#
# m68k.py
#
# wrapper for musashi m68k CPU emulator
#

import os
from ctypes import *
#import ctypes.util

# --- Constants ---

# cpu type
M68K_CPU_TYPE_INVALID = 0
M68K_CPU_TYPE_68000   = 1
M68K_CPU_TYPE_68010   = 2
M68K_CPU_TYPE_68EC020 = 3
M68K_CPU_TYPE_68020   = 4

# registers
M68K_REG_D0           = 0
M68K_REG_D1           = 1
M68K_REG_D2           = 2
M68K_REG_D3           = 3
M68K_REG_D4           = 4
M68K_REG_D5           = 5
M68K_REG_D6           = 6
M68K_REG_D7           = 7
M68K_REG_A0           = 8
M68K_REG_A1           = 9
M68K_REG_A2           = 10
M68K_REG_A3           = 11
M68K_REG_A4           = 12
M68K_REG_A5           = 13
M68K_REG_A6           = 14
M68K_REG_A7           = 15
M68K_REG_PC           = 16 # Program Counter
M68K_REG_SR           = 17 # Status Register
M68K_REG_SP           = 18 #The current Stack Pointer (located in A7)
M68K_REG_USP          = 19 # User Stack Pointer
M68K_REG_ISP          = 20 # Interrupt Stack Pointer
M68K_REG_MSP          = 21 # Master Stack Pointer
M68K_REG_SFC          = 22 # Source Function Code
M68K_REG_DFC          = 23 # Destination Function Code
M68K_REG_VBR          = 24 # Vector Base Register
M68K_REG_CACR         = 25 # Cache Control Register
M68K_REG_CAAR         = 26 # Cache Address Register

M68K_REG_PREF_ADDR    = 27 # Virtual Reg: Last prefetch address
M68K_REG_PREF_DATA    = 28 # Virtual Reg: Last prefetch data

M68K_REG_PPC          = 29 # Previous value in the program counter
M68K_REG_IR           = 30 # Instruction register
M68K_REG_CPU_TYPE     = 31 # Type of CPU being run

# interrupts
M68K_IRQ_NONE         = 0
M68K_IRQ_1            = 1
M68K_IRQ_2            = 2
M68K_IRQ_3            = 3
M68K_IRQ_4            = 4
M68K_IRQ_5            = 5
M68K_IRQ_6            = 6
M68K_IRQ_7            = 7

M68K_MODE_READ        = ord('R')
M68K_MODE_WRITE       = ord('W')
M68K_MODE_FETCH       = ord('I')

# --- Internal ---

# get lib
def find_lib():
        path = os.path.dirname(os.path.realpath(__file__))
        all_files = os.listdir(path)
        for f in all_files:
                if f.find('libmusashi') != -1:
                        return os.path.join(path,f)
        raise ImportError("Can't find musashi native lib")

lib_file = find_lib()
lib = CDLL(lib_file)

# define CPU function types for callbacks
read_func_type                   = CFUNCTYPE(c_uint, c_uint)
write_func_type                  = CFUNCTYPE(None, c_uint, c_uint)
pc_changed_callback_func_type    = CFUNCTYPE(None, c_uint, c_uint)
reset_instr_callback_func_type   = CFUNCTYPE(None)
invalid_func_type                = CFUNCTYPE(None, c_int, c_int, c_uint)
trace_func_type                  = CFUNCTYPE(c_int, c_int, c_int, c_uint, c_uint)
instr_hook_callback_func         = CFUNCTYPE(None)

# declare cpu functions
cpu_init_func                    = lib.m68k_init

execute_func                     = lib.m68k_execute
execute_func.restype             = c_int
execute_func.argtypes            = [c_int]

get_reg_func                     = lib.m68k_get_reg
get_reg_func.restype             = c_uint
get_reg_func.argtypes            = [c_void_p, c_int]

set_reg_func                     = lib.m68k_set_reg
set_reg_func.argtypes            = [c_int, c_uint]

disassemble_func                 = lib.m68k_disassemble
disassemble_func.restype         = c_int
disassemble_func.argtypes        = [c_char_p, c_uint, c_uint]

set_irq_func                     = lib.m68k_set_irq
set_irq_func.argtypes            = [c_uint]

cycles_run_func                  = lib.m68k_cycles_run
cycles_run_func.restype          = c_int

cycles_remaining_func            = lib.m68k_cycles_remaining
cycles_remaining_func.restype    = c_int

modify_timeslice_func            = lib.m68k_modify_timeslice
modify_timeslice_func.argtypes   = [c_int]

# declare mem functions
mem_init_func                    = lib.mem_init
mem_init_func.restype            = c_int
mem_init_func.argtypes           = [c_uint]

mem_free_func                    = lib.mem_free

mem_set_trace_mode_func          = lib.mem_set_trace_mode
mem_set_trace_mode_func.argtypes = [c_int]

mem_set_device_func              = lib.mem_set_device
mem_set_device_func.argtypes     = [c_uint]

mem_is_end_func                  = lib.mem_is_end
mem_is_end_func.restype          = c_int

# public
mem_ram_read                     = lib.mem_ram_read
mem_ram_read.restype             = c_uint
mem_ram_read.argtypes            = [c_int, c_uint]

mem_ram_write                    = lib.mem_ram_write
mem_ram_write.argtypes           = [c_int, c_uint, c_uint]

mem_ram_read_block               = lib.mem_ram_read_block
mem_ram_read_block.argtypes      = [c_uint, c_uint, c_char_p]

mem_ram_write_block              = lib.mem_ram_write_block
mem_ram_write_block.argtypes     = [c_uint, c_uint, c_char_p]

mem_ram_clear_block              = lib.mem_ram_clear_block
mem_ram_clear_block.argtypes     = [c_uint, c_uint, c_int]

# --- CPU API ---

def cpu_init():
        cpu_init_func()

def set_pc_changed_callback(func):
        global pc_changed_callback
        pc_changed_callback = pc_changed_callback_func_type(func)
        lib.m68k_set_pc_changed_callback(pc_changed_callback)

def set_reset_instr_callback(func):
        global reset_instr_callback
        reset_instr_callback = reset_instr_callback_func_type(func)
        lib.m68k_set_reset_instr_callback(reset_instr_callback)

def set_instr_hook_callback(func):
        global instr_hook_callback
        instr_hook_callback = instr_hook_callback_func(func)
        lib.m68k_set_instr_hook_callback(instr_hook_callback)

def set_cpu_type(t):
        lib.m68k_set_cpu_type(c_uint(t))

def pulse_reset():
        lib.m68k_pulse_reset()

def set_irq(level):
        set_irq_func(level)

def execute(cycles):
        return execute_func(cycles)

def get_reg(reg):
        return get_reg_func(None, reg)

def set_reg(reg, value):
        set_reg_func(reg, value)

def cycles_run():
        return cycles_run_func()

def cycles_remaining():
        return cycles_remaining_func()

def modify_timeslice(cycles):
        modify_timeslice_func(cycles)

def end_timeslice():
        lib.m68k_end_timeslice()

__dis_buf = create_string_buffer(80)

def disassemble(pc, cpu_type):
        n = disassemble_func(__dis_buf, pc, cpu_type)
        return __dis_buf.value

# --- MEM API ---

def mem_init(ram_size_kib):
        return mem_init_func(ram_size_kib)

def mem_free():
        mem_free_func()

def mem_set_invalid_func(func):
        global invalid_func_callback
        invalid_func_callback = invalid_func_type(func)
        lib.mem_set_invalid_func(invalid_func_callback)

def mem_set_trace_mode(on):
        __mem_tracing = on
        mem_set_trace_mode_func(on)

def mem_set_trace_func(func):
        global trace_func_callback
        trace_func_callback = trace_func_type(func)
        lib.mem_set_trace_func(trace_func_callback)
  
def mem_set_device(addr):
        mem_set_device_func(addr)

def mem_set_device_handler(func):
        global device_func_callback
        device_func_callback = trace_func_type(func)
        lib.mem_set_device_handler(device_func_callback)

def mem_is_end():
        return mem_is_end_func()
  
