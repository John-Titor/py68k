#!/usr/bin/python
#
# A M68K emulator for development purposes
#

import os, argparse, subprocess, time
import device
from musashi.m68k import (
	cpu_init,
	disassemble,
	end_timeslice,
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
	M68K_REG_SP
)
from elftools.elf.elffile import ELFFile
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
		global args

		self._emu = emu
		self._lineinfo_cache = dict()
		self._addr2line = args.addr2line

		elf_fd = open(image_filename, "rb")
		self._elf = ELFFile(elf_fd)

		if self._elf.header['e_type'] != 'ET_EXEC':
			raise RuntimeError('not an ELF executable file')
		if self._elf.header['e_machine'] != 'EM_68K':
			raise RuntimeError('not an M68K ELF file')
		if self._elf.num_segments() == 0:
			raise RuntimeError('no segments in ELF file')


		# iterate the memory segments in the file
		for segment in self._elf.iter_segments():
			p_vaddr = segment['p_vaddr']
			p_memsize = segment['p_memsz']
			p_end = p_vaddr + p_memsize

			# print some info about what we are loading
			self._emu.trace('{:#x}/{:#x} '.format(p_vaddr, p_memsize))
			for section in self._elf.iter_sections():
				if segment.section_in_segment(section):
					self._emu.trace('    {:16}: {:#x}/{:#x}'.format(section.name,
											section['sh_addr'],
											section['sh_size']))

			# XXX should really be a call on the emulator
			mem_ram_write_block(p_vaddr, p_memsize, segment.data())


	def lineinfo(self, addr):
		if addr in self._lineinfo_cache:
			return self._lineinfo_cache[addr]

		symb = subprocess.Popen([self._addr2line, 
					 '-apfiC',
					 '-e',
					 args.image,
					 '{:#x}'.format(addr)],
					stdout=subprocess.PIPE)
		output, err = symb.communicate()

		self._lineinfo_cache[addr] = output
		return output

class emulator(object):

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

	device_base = 0xff0000

	def __init__(self, image_filename, memory_size, trace_filename):

		# initialise the trace file
		self._trace_file = open(trace_filename, "w")

		# allocate memory for the emulation
		mem_init(memory_size)

		# intialise the CPU
		self._cpu_type = M68K_CPU_TYPE_68000
		set_cpu_type(self._cpu_type)
		cpu_init()

		# attach callback functions
		set_instr_hook_callback(self.trace_instruction)
		set_reset_instr_callback(self.trace_reset)
		set_pc_changed_callback(self.trace_jump)
		mem_set_trace_func(self.trace_memory)
		mem_set_invalid_func(self.buserror)

		# enable memory tracing
		mem_set_trace_mode(1)

		# configure device space
		self._root_device = device.root_device(self, self.device_base)

		# load the executable image
		self._image = image(self, image_filename)

		# reset the CPU ready for execution
		pulse_reset()

	def run(self):
		execute(100000)

	def add_device(self, dev, offset):
		"""
		Attach a device to the emulator at the given offset in device space
		"""
		dev(offset)

	def trace(self, msg):
		global emu
		self._trace_file.write(msg + '\n')

	def trace_nonl(self, msg):
		global emu
		self._trace_file.write(msg)

	def buserror(self, mode, width, addr):
		"""
		Handle an invalid memory access
		"""

		if chr(mode) == 'W':
			cause = 'write to'
		else:
			cause = 'read from'
	
		self.trace('BUS ERROR:     {:#10x}: {} invalid memory'.format(addr, cause))
		self.trace('               {}'.format(self._image.lineinfo(get_reg(M68K_REG_PPC))))
	
		end_timeslice()

	def trace_memory(self, mode, width, addr, value):
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
			self.trace('{}         {:#10x}: {:#04x}'.format(direction, addr, value))
		elif width == 1:
			self.trace('{}         {:#10x}: {:#06x}'.format(direction, addr, value))
		elif width == 2:
			self.trace('{}         {:#10x}: {:#010x}'.format(direction, addr, value))
	
		return 0
	
	def trace_instruction(self):
		"""
		Cut an instruction trace entry
		"""
		pc = get_reg(M68K_REG_PC)
		dis = disassemble(pc, self._cpu_type)
		info = ''
		for reg in self.registers:
			if dis.find(reg) is not -1:
				info += ' {}={:#x}'.format(reg, get_reg(self.registers[reg]))
	
		self.trace('EXECUTE:       {:#10x}: {:30}    {}'.format(pc, dis, info))

	def trace_reset(self):
		# normally going to exit here...
		end_timeslice()
	

	def trace_jump(self, new_pc):
		"""
		Cut a jump trace entry, called when the PC changes significantly
		"""
		self.trace_nonl('\nJUMP:          {}'.format(self._image.lineinfo(new_pc)))



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

# get an emulator
emu = emulator(memory_size = args.memory_size,
	       image_filename = args.image,
	       trace_filename = args.trace_file)

# add a UART to it
emu.add_device(device.uart, 0)

# run some instructions
emu.run()
