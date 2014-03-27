#!/usr/local/bin/pypy
#
# A M68K emulator for development purposes
#

import os, argparse, subprocess, time
from bisect import bisect
import device
from musashi.m68k import (
	cpu_init,
	disassemble,
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
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.constants import SH_FLAGS
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

		self._emu = emu
		self._lineinfo_cache = dict()
		self._symbol_cache = dict()
		self._address_cache = dict()
		self._addr2line = self._findtool('m68k-elf-addr2line')
		self._text_base = 0
		self._text_end = 0
		self._low_sym = 0xffffffff
		self._high_sym = 0

		if self._addr2line is None:
			raise RuntimeError("unable to find m68k-elf-addr2line and/or m68k-elf-readelf, check your PATH")

		elf_fd = open(image_filename, "rb")
		self._elf = ELFFile(elf_fd)

		if self._elf.header['e_type'] != 'ET_EXEC':
			raise RuntimeError('not an ELF executable file')
		if self._elf.header['e_machine'] != 'EM_68K':
			raise RuntimeError('not an M68K ELF file')
		if self._elf.num_segments() == 0:
			raise RuntimeError('no segments in ELF file')

		# iterate sections
		for section in self._elf.iter_sections():

			# does this section need to be loaded?
			if section['sh_flags'] & SH_FLAGS.SHF_ALLOC:
				p_addr = section['sh_addr']	
				p_size = section['sh_size']
				self._emu.log('{} {:#x}/{:#x} '.format(section.name, p_addr, p_size))

				# XXX should really be a call on the emulator
				mem_ram_write_block(p_addr, p_size, section.data())

				if section.name == '.text':
					self._text_base = p_addr
					self._text_end = p_addr + p_size

			# does it contain symbols?
			if isinstance(section, SymbolTableSection):
				self._cache_symbols(section)

		self._symbol_index = sorted(self._symbol_cache.keys())

	def _cache_symbols(self, section):

		for nsym, symbol in enumerate(section.iter_symbols()):

			# only interested in data and function symbols
			s_type = symbol['st_info']['type']
			if s_type != 'STT_OBJECT' and s_type != 'STT_FUNC':
				continue

			s_addr = symbol['st_value']
			s_size = symbol['st_size']
			s_name = str(symbol.name)

			self._low_sym = min(s_addr, self._low_sym)
			self._high_sym = max(s_addr + s_size, self._high_sym)

			self._symbol_cache[s_addr] = { 'name': s_name, 'size' : s_size }
			self._address_cache[s_name] = s_addr

	def _findtool(self, tool):
		for path in os.environ['PATH'].split(os.pathsep):
			path = path.strip('"')
			candidate = os.path.join(path, tool)
			if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
				return candidate
		return None

	def lineinfo(self, addr):
		try:
			return self._lineinfo_cache[addr]

		except KeyError:

			# -i gives extra information about inlined functions, but it puts
			# newlines in the result that mess up the log...

			symb = subprocess.Popen([self._addr2line, 
						 '-pfC',
						 '-e',
						 args.image,
						 '{:#x}'.format(addr)],
						stdout=subprocess.PIPE)
			output, err = symb.communicate()

			self._lineinfo_cache[addr] = output
			return output

	def symname(self, addr):
		if addr < self._low_sym or addr >= self._high_sym:
			return ''

		try:
			return self._symbol_cache[addr]['name']

		except KeyError:
			# look for the next highest symbol address
			pos = bisect(self._symbol_index, addr)
			if pos == 0:
				# address lower than anything we know
				return ''
			insym = self._symbol_index[pos - 1]

			# check that the value is within the symbol
			delta = addr - insym
			if self._symbol_cache[insym]['size'] <= delta:
				return ''

			# it is, construct a name + offset string 
			name = '{}+{:#x}'.format(self._symbol_cache[insym]['name'], delta)

			# add it to the symbol cache
			self._symbol_cache[addr] = { 'name': name, 'size' : 1 }

			return name

	def symrange(self, name):
		try:
			addr = self._address_cache[name]
			size = self._symbol_cache[addr]['size']
		except KeyError:
			try:
				addr = int(name)
				size = 1
			except:
				raise RuntimeError('can\'t find a symbol called {} and can\'t convert it to an address'.format(name))

		return range(addr, addr + size)

	def check_text(self, addr):
		if addr < self._text_base or addr >= self._text_end:
			return False
		return True

class emulator(object):

	registers = {
		'D0'  : M68K_REG_D0,
		'D1'  : M68K_REG_D1,
		'D2'  : M68K_REG_D2,
		'D3'  : M68K_REG_D3,
		'D4'  : M68K_REG_D4,
		'D5'  : M68K_REG_D5,
		'D6'  : M68K_REG_D6,
		'D7'  : M68K_REG_D7,
		'A0'  : M68K_REG_A0,
		'A1'  : M68K_REG_A1,
		'A2'  : M68K_REG_A2,
		'A3'  : M68K_REG_A3,
		'A4'  : M68K_REG_A4,
		'A5'  : M68K_REG_A5,
		'A6'  : M68K_REG_A6,
		'A7'  : M68K_REG_A7,
		'PC'  : M68K_REG_PC,
		'SR'  : M68K_REG_SR,
		'SP'  : M68K_REG_SP,
		'USP' : M68K_REG_USP,
		'SSP' : M68K_REG_ISP
	}

	device_base = 0xff0000
	cpu_frequency = 8

	def __init__(self, image_filename, memory_size, trace_filename):

		self._dead = False
		self._interrupted = False

		# initialise tracing
		self._trace_file = open(trace_filename, "w")
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
		self._elapsed_time = 0
		self._device_deadline = 0
		self._quantum = self.cpu_frequency * 100

		# intialise the CPU
		self._cpu_type = M68K_CPU_TYPE_68000
		set_cpu_type(self._cpu_type)
		cpu_init()

		# attach unconditional callback functions
		set_reset_instr_callback(self.cb_trace_reset)
		mem_set_invalid_func(self.cb_buserror)

		# enable memory tracing
		mem_set_trace_mode(1)

		# configure device space
		self._root_device = device.root_device(self, self.device_base)

		# load the executable image
		self._image = image(self, image_filename)

		# reset the CPU ready for execution
		pulse_reset()


	def run(self, cycle_limit = float('inf')):
		self._cycle_limit = cycle_limit
		while not self._dead:
			try:
				start_time = time.time()
				self._root_device.tick(self.current_time)
				self._elapsed_cycles += execute(self._quantum)
				self._elapsed_time += time.time() - start_time
			except KeyboardInterrupt:
				self._keyboard_interrupt()

			if mem_is_end():
				self._fatal('illegal memory access')

			if self._elapsed_cycles > self._cycle_limit:
				self._fatal('cycle limit exceeded')

		self.log('\nterminating: {}'.format(self._postmortem))


	def finish(self):
		self.log('{} cycles in {} seconds, {} cps'.format(self._elapsed_cycles,
							     self._elapsed_time,
							     int(self._elapsed_cycles / self._elapsed_time)))

		try:
			self._trace_file.flush()
			self._trace_file.close()
		except Exception:
			pass


	def add_device(self, dev, offset, interrupt = -1):
		"""
		Attach a device to the emulator at the given offset in device space
		"""
		self._root_device.add_device(dev, offset, interrupt)


	@property
	def current_time(self):
		return self._elapsed_cycles / self.cpu_frequency


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
			self._cycle_limit = min(self._cycle_limit, self._elapsed_cycles + self._trace_cycle_limit)
	

	def log(self, msg):
		print msg
		self._trace_file.write(msg + '\n')


	def cb_buserror(self, mode, width, addr):
		"""
		Handle an invalid memory access
		"""
		try:
			if mode == M68K_MODE_WRITE:
				cause = 'write to'
			else:
				cause = 'read from'
		
			self.trace('BUS ERROR', addr, self._image.lineinfo(get_reg(M68K_REG_PPC)))
			self._fatal('BUS ERROR during {} {} - invalid memory'.format(cause, addr))

		except KeyboardInterrupt:
			self._keyboard_interrupt()


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

		except KeyboardInterrupt:
			self._keyboard_interrupt()

		return 0


	def cb_trace_instruction(self):
		"""
		Cut an instruction trace entry
		"""
		try:
			pc = get_reg(M68K_REG_PC)
			if not self._trace_instructions and pc in self._trace_instruction_triggers:
					self._trace_trigger(pc, 'instruction', ['instructions', 'jumps'])

			if self._trace_instructions:
				dis = disassemble(pc, self._cpu_type)
				info = ''
				for reg in self.registers:
					if dis.find(reg) is not -1:
						info += ' {}={:#x}'.format(reg, get_reg(self.registers[reg]))
			
				self.trace('EXECUTE', pc, '{:30} {}'.format(dis, info))

		except KeyboardInterrupt:
			self._keyboard_interrupt()


	def cb_trace_reset(self):
		"""
		Trace reset instructions
		"""
		try:
			# might want to end here due to memory issues
			end_timeslice()

			# devices must reset
			self._root_device.reset()
	
		except KeyboardInterrupt:
			self._keyboard_interrupt()


	def cb_trace_jump(self, new_pc, vector):
		"""
		Cut a jump trace entry, called when the PC changes significantly, usually
		a function call, return or exception
		"""
		try:
			if vector == 0:
				if self._trace_jumps:
					self.trace('JUMP', new_pc, self._image.lineinfo(new_pc))

				if self._check_PC_in_text:
					if not self._image.check_text(new_pc):
						self._fatal('PC {:#x} not in .text'.format(new_pc))
			else:
				if vector in self._trace_exception_list:
					ppc = get_reg(M68K_REG_PPC)
					self.trace('EXCEPTION', ppc, 'vector {:#x} to {}'.format(vector, self._image.lineinfo(new_pc)))

		except KeyboardInterrupt:
			self._keyboard_interrupt()


	def _keyboard_interrupt(self):
		self._fatal('user interrupt')

	def _fatal(self, reason):
		self._dead = True
		self._postmortem = reason
		end_timeslice()


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
parser.add_argument('--trace-cycle-limit',
		    type=int,
		    default=0,
		    metavar='CYCLES',
		    help='stop the emulation after CYCLES following an instruction or memory trigger')
parser.add_argument('--trace-check-PC-in-text',
		    action='store_true',
		    help='when tracing instructions, stop if the PC lands outside the text section')
parser.add_argument('image',
		    help='ELF executable to load')
args = parser.parse_args()

# get an emulator
emu = emulator(memory_size = args.memory_size,
	       image_filename = args.image,
	       trace_filename = args.trace_file)

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

# add some devices
emu.add_device(device.uart, 0, M68K_IRQ_2)
emu.add_device(device.timer, 0x1000, M68K_IRQ_6)

# run some instructions
emu.run(args.cycle_limit)

emu.finish()
