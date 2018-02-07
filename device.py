import sys
from musashi.m68k import (
	set_irq,
	set_int_ack_callback,
	mem_set_device,
	mem_set_device_handler
)

class device(object):
	"""
	Generic device model
	"""
	_register_to_device = dict()
	_devices = list()

	MODE_READ = 'R'
	MODE_WRITE = 'W'
	WIDTH_8 = 0
	WIDTH_16 = 1
	WIDTH_32 = 2

	def __init__(self):
		self._debug = False

	def map_registers(self, registers):
		"""
		Map device registers
		"""
		self._register_name_map = {}
		for reg in registers:
			addr = self._device_base + registers[reg]
			if (addr in device._register_to_device): 
				other = device._register_to_device[addr]
				if self != other:
					raise RuntimeError('register at {} already assigned to {}'.format(addr, other._name))
			device._register_to_device[addr] = self
			device._emu.trace('DEVICE', info='add register {}/0x{:x} for {}'.format(reg, registers[reg], self._name))
			self._register_name_map[registers[reg]] = reg


	def trace(self, action, info=''):
		if self._debug:
			device._emu.trace('DEVICE', info='{}: {} {}'.format(self._name, action, info))

	def tick(self, current_time):
		return 0

	def reset(self):
		return

	def get_vector(self):
		return M68K_IRQ_SPURIOUS

	def get_register_name(self, addr):
		return self._register_name_map[addr]

class root_device(device):

	def __init__(self, emu, base):
		"""
		Initialise the root device
		"""
		self._debug = False
		self._name = 'root'
		device._emu = emu
		device._root_device = self
		device._device_base = base
		set_int_ack_callback(self.int_callback)
		mem_set_device_handler(self._access)

	def _access(self, mode, width, addr, value):
		self.trace('access', '{}'.format(addr))
		self.trace('mappings', device._register_to_device)

		# look for a device
		if addr not in device._register_to_device:
			self.trace('lookup', 'failed to find device to handle access')
			device._emu.cb_buserror(mode, width, addr)
			return 0
		else:
			# dispatch to device emulator
			dev_addr = addr - device._device_base
			return device._register_to_device[addr].access(chr(mode), width, dev_addr, value)

	def add_device(self, dev, offset, interrupt = -1, debug = False):
		new_dev = dev(offset, interrupt, debug)
		device._devices.append(new_dev)
		mem_set_device(device._device_base + offset);

	def tick(self, current_time):
		deadline = 0
		for dev in device._devices:
			ret = dev.tick(current_time)
			if ret > 0 and (deadline == 0 or ret < deadline):
				deadline = ret
		return deadline

	def reset(self):
		for dev in device._devices:
			dev.reset()

	def int_callback(self, interrupt):
		for dev in device._devices:
			vector = dev.get_vector(interrupt)
			if vector != M68K_IRQ_SPURIOUS:
				return vector
		return M68K_IRQ_SPURIOUS

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

	def access(self, mode, width, addr, value):
		if mode == device.MODE_READ:
			if addr == self._registers['SR']:
				value = 0
				if self._rx_ready:
					value |= SR_RXRDY
				if self._tx_ready:
					value |= SR_TXRDY
			elif addr == self._registers['DR']:
				value = self._rx_data

		elif mode == device.MODE_WRITE:
			if addr == self._registers['DR']:
				self.trace('write', '{}'.format(chr(value).__repr__()))
				# XXX this is a bit hokey...
				try:
					sys.stdout.write(chr(value))
					sys.stdout.flush()
				except KeyboardInterrupt:
					raise KeyboardInterrupt
				except Exception:
					pass

		return value

	def tick(self, current_time):
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

	def access(self, mode, width, addr, value):
		if mode == device.MODE_READ:
			if addr == self._registers['RELOAD']:
				value = self._reload
			if addr == self._registers['COUNT']:
				# force a tick to make sure we have caught up with time
				self.tick(device._emu.current_time)
				value = self._count	

		elif mode == device.MODE_WRITE:
			if addr == self._registers['RELOAD']:
				self.trace('set reload', '{}'.format(value))
				self._reload = value
				self._count = self._reload
				self._last_update = device._emu.current_time

		return value

	def tick(self, current_time):

		# do nothing if we are disabled
		if self._reload == 0:
			return 0

		# how much time has elapsed?
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

