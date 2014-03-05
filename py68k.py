#!/usr/bin/python
#
# A M68K emulator for development purposes
#

import os, argparse, subprocess
from musashi.m68k import (
	cpu_init,
	disassemble,
	execute,
	get_reg,
	mem_init,
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
	M68K_REG_SR,
	M68K_REG_SP
)
from elftools.elf.elffile import ELFFile
from elftools.elf.descriptions import (
	describe_e_machine,
	describe_e_type
)

registers = {
	'D0' : M68K_REG_D0,
	'D1' : M68K_REG_D1,
	'D2' : M68K_REG_D2,
	'D3' : M68K_REG_D3,
	'D4' : M68K_REG_D4,
	'D5' : M68K_REG_D5,
	'D6' : M68K_REG_D6,
	'D7' : M68K_REG_D7,
	'A0' : M68K_REG_A0,
	'A1' : M68K_REG_A1,
	'A2' : M68K_REG_A2,
	'A3' : M68K_REG_A3,
	'A4' : M68K_REG_A4,
	'A5' : M68K_REG_A5,
	'A6' : M68K_REG_A6,
	'A7' : M68K_REG_A7,
	'PC' : M68K_REG_PC,
	'SR' : M68K_REG_SR,
	'SP' : M68K_REG_SP}

def trace(msg):
	global trace_file
	trace_file.write(msg + '\n')

def trace_nonl(msg):
	global trace_file
	trace_file.write(msg)

def xlineinfo(addr):
	"""
	Ask addr2line for information about an address
	"""
	global symbolicator, lineinfo_cache

	if addr in lineinfo_cache:
		return lineinfo[addr]

	symbolicator.stdin.write('{:#x}\n'.format(addr))
	info = symbolicator.stdout.readline()

	lineinfo_cache[addr] = info
	return info

def lineinfo(addr):
	global args

	symb = subprocess.Popen([args.addr2line, '-apfiC', '-e', args.image, '{:#x}'.format(addr)], stdout=subprocess.PIPE)
	output, err = symb.communicate()

	return output

def invalid(mode, width, addr):
	trace('INVALID: {}({}): {:#10x}'.format(chr(mode), width, addr))


def trace_memory(mode, width, addr, value):
	"""
	Cut a memory trace entry
	"""
	# don't trace immediate fetches, since they are described by the disassembly
	kind = chr(mode)
	if kind == 'I':
		return 0
	if kind == 'W':
		direction = "WRITE:"
	else:
		direction = "READ: "

	if width == 0:
		trace('{}         {:#10x}: {:#04x}'.format(direction, addr, value))
	elif width == 1:
		trace('{}         {:#10x}: {:#06x}'.format(direction, addr, value))
	elif width == 2:
		trace('{}         {:#10x}: {:#010x}'.format(direction, addr, value))

	return 0


def trace_instruction():
	"""
	Cut an instruction trace entry
	"""
	pc = get_reg(M68K_REG_PC)
	dis = disassemble(pc, cpu_type)
	info = ''
	for reg in registers:
		if dis.find(reg) is not -1:
			info += ' {}={:#x}'.format(reg, get_reg(registers[reg]))

	trace('EXECUTE:       {:#10x}: {:30}    {}'.format(pc, dis, info))


def trace_reset():
	trace('RESET')


def trace_jump(new_pc):
	"""
	Cut a jump trace entry, called when the PC changes significantly
	"""
	trace_nonl('\nJUMP:          {}'.format(lineinfo(new_pc)))


def init_elf():
	"""
	Read the ELF headers and prepare to load the executable
	"""
	global args, elf

	elf_fd = open(args.image, "rb")
	elf = ELFFile(elf_fd)

	if elf.header['e_type'] != 'ET_EXEC':
		raise RuntimeError('not an ELF executable file')
	if elf.header['e_machine'] != 'EM_68K':
		raise RuntimeError('not an M68K ELF file')
	if elf.num_segments() == 0:
		raise RuntimeError('no segments in ELF file')


def init_cpu():
	"""
	Initialise the CPU for the supplied ELF file
	"""
	global args, elf, cpu_type

	# XXX should be able to infer this from the ELF file
	cpu_type = M68K_CPU_TYPE_68000

	cpu_init()
	set_cpu_type(cpu_type)


def init_memory():
	"""
	Initialise memory for the supplied ELF file
	"""
	global args, elf

	mem_init(args.memory_size)
	mem_set_invalid_func(invalid)

	# iterate the memory segments in the file
	for segment in elf.iter_segments():
		p_vaddr = segment['p_vaddr']
		p_memsize = segment['p_memsz']
		p_end = p_vaddr + p_memsize

		# XXX memory starts at zero for now
		if (p_end > (args.memory_size * 1024)):
			raise RuntimeError('memory size {} too small, need at least {}'.format(
							args.memory_size, (max_addr + 1023) / 1024))

		# print some info about what we are loading
		print '{:#x}/{:#x} '.format(p_vaddr, p_memsize)
		for section in elf.iter_sections():
			if segment.section_in_segment(section):
				print '    {:16}: {:#x}/{:#x}'.format(section.name, section['sh_addr'], section['sh_size'])

		mem_ram_write_block(p_vaddr, p_memsize, segment.data())


def init_tracing():
	"""
	Initialise tracing
	"""
	global args, trace_file

	trace_file = open(args.trace_file, "w")

	mem_set_trace_func(trace_memory)
	mem_set_trace_mode(1)
	set_instr_hook_callback(trace_instruction)
	set_reset_instr_callback(trace_reset)
	set_pc_changed_callback(trace_jump)


def init_symbolicator():
	"""
	Kick off addr2line so that we can look up branch targets
	"""
	global args, symbolicator, lineinfo_cache

	lineinfo_cache = {}

	symbolicator = subprocess.Popen([args.addr2line, '-fpC', '-e', args.image, '@-'],
					shell=False,
					bufsize=1,
					stdin=subprocess.PIPE,
					stdout=subprocess.PIPE,
					stderr=subprocess.STDOUT)
	if symbolicator is None:
		raise RuntimeError('failed to launch {}'.format(args.addr2line))
	if symbolicator.poll() is not None:
		raise RuntimeError('{} exited before being used'.format(args.addr2line))

# Parse commandline arguments
parser = argparse.ArgumentParser(description='m68k emulator')
parser.add_argument('--memory-size',
		    type=int,
		    default=128,
		    help='memory size in KiB')
parser.add_argument('--trace-file',
		    type=str,
		    default='trace.out',
		    help='trace output file')
parser.add_argument('--addr2line',
		    type=str,
		    default='m68k-elf-addr2line',
		    help='path to invoke the addr2line utility')
parser.add_argument('image',
		    help='ELF executable to load')
args = parser.parse_args()

# init image file
init_elf()

# start the symbolicator
#init_symbolicator()

# cpu initialisation
init_cpu()

# memory configuration
init_memory()

# trace initialisation
init_tracing()

# reset the CPU ready for execution
pulse_reset()

# run some instructions
print 'running'
execute(100000)
