import sys
from musashi.m68k import (
	set_irq,
	set_int_ack_callback,
	mem_set_device,
	mem_set_device_handler,
	get_reg,
	M68K_REG_SR,
	M68K_IRQ_SPURIOUS,
	M68K_IRQ_AUTOVECTOR
)

class device(object):
	"""
	Generic device model

	Properties that can / should be set by instances:

	_name		text name of the instance
	_address	absolute base address of the instance or None if no registers
	_interrupt	IPL asserted by the device or None if not interrupting
	_debug		True to enable tracing

	"""
	_register_to_device = dict()
	_devices = list()
	_emu = None

	root_device = None

	MODE_READ = 'R'
	MODE_WRITE = 'W'
	WIDTH_8 = 0
	WIDTH_16 = 1
	WIDTH_32 = 2

	def __init__(self, name, address = None, interrupt = None, debug = False):
		self._name = name
		self._address = address
		self._interrupt = interrupt
		self._debug = debug

	def map_registers(self, registers):
		"""
		Map device registers
		"""
		if self._address is None:
			raise RuntimeError('cannot map registers without base address')
		self._register_name_map = {}
		for reg in registers:
			regaddr = self._address + registers[reg]
			if (regaddr in device._register_to_device): 
				other = device._register_to_device[regaddr]
				if self != other:
					raise RuntimeError('register at {} already assigned to {}'.format(regaddr, other._name))
			device._register_to_device[regaddr] = self
#			device._emu.trace('DEVICE', address = regaddr, info='add register {}/0x{:x} for {}'.format(reg, registers[reg], self._name))
			self._register_name_map[registers[reg]] = reg

	def trace(self, action, info=''):
		"""
		Emit a debug trace message
		"""
		if self._debug:
			device._emu.trace('DEVICE', info='{}: {} {}'.format(self._name, action, info))

	def get_register_name(self, offset):
		return self._register_name_map[offset]

	@property
	def current_time(self):
		return self.root_device._emu.current_time

	@property
	def current_cycle(self):
		return self.root_device._emu.current_cycle

	@property
	def cycle_rate(self):
		return self.root_device._emu.cpu_frequency


	#
	# Methods that should be implemented by device models
	#

	def read(self, width, offset):
		"""
		Called when a CPU read access decodes to one of the registers defined in a call to map_registers.
		width is one of device.WIDTH_8, device.WIDTH_16 or device.WIDTH_32
		offset is the register offset from the device base address
		Function should return the read value.
		"""
		return 0

	def write(self, width, offset, value):
		"""
		Called when a CPU write access decodes to one of the registers defined in a call to map_registers.
		width is one of device.WIDTH_8, device.WIDTH_16 or device.WIDTH_32
		offset is the register offset from the device base address
		value is the value being written
		"""
		pass

	def tick(self, elapsed_cycles, current_time):
		"""
		Called every emulator tick
		"""
		return 0

	def reset(self):
		"""
		Called at emulator reset time
		"""
		return

	def get_interrupt(self):
		"""
		Called to determine whether the device is interrupting; should return the device
		IPL if interrupting or 0 if not.
		"""
		return 0

	def get_vector(self):
		"""
		Called during the interrupt acknowledge phase. Should return a programmed vector or
		M68K_IRQ_AUTOVECTOR as appropriate if the device is interrupting, or M68K_IRQ_SPURIOUS
		otherwise.
		"""
		return M68K_IRQ_SPURIOUS


class root_device(device):

	_console_output_driver = None
	_console_input_driver = None

	def __init__(self, emu, address, debug = False):
		super(root_device, self).__init__('root', address = address, debug = debug)
		device._emu = emu
		device._device_base = address
		device.root_device = self

		set_int_ack_callback(self.int_callback)
		mem_set_device_handler(self.access_callback)

	def access_callback(self, mode, width, address, value):
		#self.trace('access', '{}'.format(address))
		#self.trace('mappings', device._register_to_device)

		# look for a device
		if address not in device._register_to_device:
			self.trace('lookup', 'failed to find device to handle access')
			device._emu.cb_buserror(mode, width, address)
			return 0
		
		# dispatch to device emulator
		try:
			offset = address - device._device_base
			dev = device._register_to_device[address]
			if chr(mode) == device.MODE_READ:
				value = dev.read(width, offset)
			else:
				dev.write(width, offset, value)
			self.check_interrupts()
		except Exception as e:
			self._emu.fatal_exception(e)

		return value

	def add_device(self, dev, address = None, interrupt = None, debug = False):
		if address is not None:
			if address < self._device_base:
				raise RuntimeError("device cannot be registered outside device space")
			mem_set_device(address);
		print dev
		new_dev = dev(address = address, interrupt = interrupt, debug = debug)
		device._devices.append(new_dev)

	def tick(self):
		deadline = 0
		for dev in device._devices:
			ret = dev.tick()
			if ret > 0 and (deadline == 0 or ret < deadline):
				deadline = ret

		self.check_interrupts()
		return deadline

	def reset(self):
		for dev in device._devices:
			dev.reset()

	def int_callback(self, interrupt):
		try:
			for dev in device._devices:
				vector = dev.get_vector(interrupt)
				if vector != M68K_IRQ_SPURIOUS:
					self.trace('{} returns vector 0x{:x}'.format(dev._name, vector))
					return vector
			self.trace('no interrupting device')
		except Exception as e:
			self._emu.fatal_exception(e)

		return M68K_IRQ_SPURIOUS


	def check_interrupts(self):
		ipl = 0
		for dev in device._devices:
			dev_ipl = dev.get_interrupt()
			if dev_ipl > ipl:
				interruptingDevice = dev
				ipl = dev_ipl
		if ipl > 0:
			SR = get_reg(M68K_REG_SR)
			cpl = (SR >> 8) & 7
			if ipl > cpl:
				self.trace('{} asserts ipl {}'.format(interruptingDevice._name, ipl))
		set_irq(ipl)

	def register_console_input_driver(self, inst):
		root_device._console_input_driver = inst

	def register_console_output_driver(self, inst):
		root_device._console_output_driver = inst

	def console_input(self, input):
		if root_device._console_input_driver is not None:
			root_device._console_input_driver.handle_console_input(input)

	def console_output(self, output):
		if root_device._console_output_driver is not None:
			root_device._console_output_driver.handle_console_output(output)

# XXX these are horribly outdated right now...

class uart(device):
	"""
	Dumb UART
	"""

	_registers = {
		'SR' : 0x00,
		'DR' : 0x02
	}
	SR_RXRDY = 0x01
	SR_TXRDY = 0x02

	def __init__(self, base, interrupt, debug=False):
		self._base = base
		self._name = "uart"
		self._interrupt = interrupt
		self._debug = debug
		self.map_registers(self._registers)
		self.reset()

	def read(self, width, addr):
		if addr == self._registers['SR']:
			value = 0
			if self._rx_ready:
				value |= SR_RXRDY
			if self._tx_ready:
				value |= SR_TXRDY
		elif addr == self._registers['DR']:
			value = self._rx_data

		return value

	def write(self, width, addr, value):
		if addr == self._registers['DR']:
			self.trace('write', '{}'.format(chr(value).__repr__()))
			sys.stdout.write(chr(value))
			sys.stdout.flush()

	def tick(self):
		# emulate tx drain, get rx data from stdin?
		return 0

	def reset(self):
		self._rx_ready = False
		self._tx_ready = True
		self._rx_data = 0

	def get_vector(self, interrupt):
		if interrupt == self._interrupt:
			return M68K_IRQ_AUTOVECTOR
		return M68K_IRQ_SPURIOUS

class timer(device):
	"""
	A simple down-counting timer
	"""

	_registers = {
		'RELOAD' : 0x00,
		'COUNT'  : 0x04
	}

	def __init__(self, base, interrupt, debug=False):
		self._base = base
		self._name = "timer"
		self._interrupt = interrupt
		self._debug = debug
		self.map_registers(self._registers)
		self.reset()

	def read(self, width, addr):
		if addr == self._registers['RELOAD']:
			value = self._reload
		if addr == self._registers['COUNT']:
			# force a tick to make sure we have caught up with time
			self.tick(device._emu.current_time)
			value = self._count	
		return value

	def write(self, width, addr, value):
		if addr == self._registers['RELOAD']:
			self.trace('set reload', '{}'.format(value))
			self._reload = value
			self._count = self._reload
			self._last_update = device._emu.current_time

	def tick(self):
		# do nothing if we are disabled
		if self._reload == 0:
			return 0

		# how much time has elapsed?
		current_time = self.current_time
		delta = (current_time - self._last_update) % self._reload
		self._last_update = current_time

		if self._count >= delta:
			# we are still counting towards zero
			self._count -= delta
		else:
			# we have wrapped, do reload & interrupt
			self.trace('tick', '')
			delta -= self._count
			self._count = self._reload - delta
			set_irq(self._interrupt)

		# send back a hint as to when we should be called again for best results
		return self._count

	def reset(self):
		self._reload = 0
		self._count = 0
		self._last_update = 0

	def get_vector(self, interrupt):
		if interrupt == self._interrupt:
			return M68K_IRQ_AUTOVECTOR
		return M68K_IRQ_SPURIOUS

