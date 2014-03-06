import sys
from musashi.m68k import (
	set_irq,
	mem_set_device,
	mem_set_device_handler
)

class device(object):
	"""
	Generic device model
	"""
	_register_to_device = dict()
	_devices = list()

	OP_READ_8 = 0
	OP_READ_16 = 1
	OP_READ_32 = 2

	MODE_READ = 'R'
	MODE_WRITE = 'W'
	WIDTH_8 = 0
	WIDTH_16 = 1
	WIDTH_32 = 2

	def map_registers(self, base, registers):
		"""
		Map device registers
		"""
		for reg in registers:
			addr = self._device_base + base + registers[reg]
			if addr in device._register_to_device:
				raise RuntimeError('register at {} already assigned'.format(addr))
			device._register_to_device[addr] = self

	def trace(self, action, info=''):
		device._emu.trace('DEVICE', info='{}: {} {}'.format(self._name, action, info))

	def tick(self, current_time):
		return 0

class root_device(device):

	def __init__(self, emu, base):
		"""
		Initialise the root device
		"""
		device._emu = emu
		device._root_device = self
		device._device_base = base
		mem_set_device(device._device_base)
		mem_set_device_handler(self._access)

	def _access(self, mode, width, addr, value):
		# look for a device
		if addr not in device._register_to_device:
			device._emu.buserror(mode, width, addr)
			return 0
		else:
			# dispatch to device emulator
			dev_addr = addr - device._device_base
			return device._register_to_device[addr].access(chr(mode), width, dev_addr, value)

	def add_device(self, dev, offset):
		new_dev = dev(offset)
		device._devices.append(new_dev)

	def tick(self, current_time):
		deadline = 0
		for dev in device._devices:
			ret = dev.tick(current_time)
			if ret > 0 and (deadline == 0 or ret < deadline):
				deadline = ret
		return deadline

class uart(device):
	"""
	Dumb UART emulation
	"""

	# registers
	_registers = {
		'SR' : 0x00,
		'DR' : 0x02
	}
	SR_RXRDY = 0x01
	SR_TXRDY = 0x02

	def __init__(self, base):
		self._base = base
		self._name = "uart"
		self._rx_ready = False
		self._tx_ready = True
		self._rx_data = 0

		self.map_registers(base, self._registers)

	def access(self, mode, width, addr, value):
		addr -= self._base
		if mode == device.MODE_READ:
			if addr == self._registers['SR']:
				value = 0
				if self._rx_ready:
					value |= SR_RXRDY
				if self._tx_ready:
					value |= SR_TXRDY
			elif addr == self._registers['DR']:
				value = self._rx_data

		if mode == device.MODE_WRITE:
			if addr == self._registers['DR']:
				self.trace('write', '{}'.format(chr(value).__repr__()))
				# XXX this is a bit hokey...
				sys.stdout.write(chr(value))
				sys.stdout.flush()

		return value

