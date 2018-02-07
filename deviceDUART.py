import sys
from device import device
from collections import deque

class _Channel():

	REG_MR		= 0x01
	REG_SR		= 0x03
	REG_RB		= 0x07
	REG_CSR		= 0x03
	REG_CR		= 0x05
	REG_TB		= 0x07

	CTRL_CMD_MASK	= 0xf0
	CTRL_BRKSTOP    = 0x70
	CTRL_BRKSTART   = 0x60
	CTRL_BRKRST     = 0x50
	CTRL_ERRST      = 0x40
	CTRL_TXRST      = 0x30
	CTRL_RXRST      = 0x20
	CTRL_MRRST      = 0x10
	CTRL_TXDIS      = 0x08
	CTRL_TXEN       = 0x04
	CTRL_RXDIS      = 0x02
	CTRL_RXEN       = 0x01

	def __init__(self, parent):
		self.reset()
		self._parent = parent

	def reset(self):
		self._mr1 = 0;
		self._mr2 = 0;
		self._mrAlt = False;
		self._sr = 0;
		self._rfifo = deque()
		self._rxEnable = False;
		self._txEnable = False;

	def access(self, mode, addr, value):
		if mode == device.MODE_READ:
			if addr == _Channel.REG_MR:
				if self._mrAlt:
					value = self._mr2
				else:
					self._mrAlt = True
					value = self._mr1

			elif addr == _Channel.REG_SR:
				value = self._sr

			elif addr == _Channel.REG_RB:
				if len(self._rfifo) > 0:
					value = self._rfifo.popleft()

			# default read result
			value = 0xff

			#self._parent.trace('{:x} -> 0x{:x}'.format(addr, value))

		if mode == device.MODE_WRITE:
			#self._parent.trace('{:x} <- 0x{:x}'.format(addr, value))

			if addr == _Channel.REG_MR:
				if self._mrAlt:
					self._mr2 = value
				else:
					self._mrAlt = True
					self._mr1 = value

			#elif addr == _Channel.REG_CSR:

			elif addr == _Channel.REG_CR:
				# rx/tx dis/enable logic
				if value & _Channel.CTRL_RXDIS:
					self._rxEnable = False
				elif value & _Channel.CTRL_RXEN:
					self._rxEnable = True
				if value & _Channel.CTRL_TXDIS:
					self._txEnable = False
				elif value & _Channel.CTRL_TXEN:
					self._txEnable = True

				cmd = value & _Channel.CTRL_CMD_MASK
				if cmd == _Channel.CTRL_MRRST:
					self._mrAlt = False
				elif cmd == _Channel.CTRL_RXRST:
					self._rxEnable = False
					self._rxfifo.clear()
				elif cmd == _Channel.CTRL_TXRST:
					self._txEnable = False
					#self._txfifo

			elif addr == _Channel.REG_TB:
				print('TX')
				# XXX this is a bit hokey...
				try:
					sys.stdout.write(chr(value))
					sys.stdout.flush()
				except KeyboardInterrupt:
					raise KeyboardInterrupt
				except Exception:
					pass

		return value


class DUART(device):

	# assuming the device is mapped to the low byte

	REG_SELMASK		= 0x18
	REG_SEL_A		= 0x00
	REG_SEL_B		= 0x10

	# non-channel registers
	REG_IPCR		= 0x09
	REG_ACR			= 0x09
	REG_ISR			= 0x0b
	REG_IMR			= 0x0b
	REG_CUR			= 0x0d
	REG_CTUR		= 0x0d
	REG_CLR			= 0x0f
	REG_CTLR		= 0x0f
	REG_IVR			= 0x19
	REG_IPR			= 0x1b
	REG_OPCR		= 0x1b
	REG_STARTCC		= 0x1d
	REG_OPRSET		= 0x1d
	REG_STOPCC		= 0x1f
	REG_OPRCLR		= 0x1f


	_registers = {
		'MRA'  	  	: 0x01,
		'SRA/CSRA'	: 0x03,
		'CRA'	  	: 0x05,
		'RBA/TBA'     	: 0x07,
		'IPCR/ACR'    	: 0x09,
		'ISR/IMR'       : 0x0b,
		'CUR/CTUR'      : 0x0d,
		'CLR/CTLR'      : 0x0f,
		'MRB'           : 0x11,
		'SRB/CSRB'      : 0x13,
		'RBB/TBB'       : 0x17,
		'IVR'           : 0x19,
		'IPR/OPCR'      : 0x1b,
		'STARTCC/OPRSET': 0x1d,
		'STOPCC/OPRCLR' : 0x1f
	}

	ACR_MODE_MASK 		= 0x70
	ACR_MODE_CTR_XTAL	= 0x30
	ACR_MODE_TMR_XTAL	= 0x60
	ACR_MODE_TMR_XTAL16	= 0x70

	def __init__(self, base, interrupt, debug = False):
		self._base = base
		self._name = 'DUART'
		self._interrupt = interrupt
		self._debug = debug
		self.map_registers(DUART._registers)

		self._a = _Channel(self);
		self._b = _Channel(self);
		self.reset()
		self.trace('init done')

	def access(self, mode, width, addr, value):

		if mode == device.MODE_READ:
			regsel = addr & DUART.REG_SELMASK
			if regsel == DUART.REG_SEL_A:
				value = self._a.access(mode, addr - DUART.REG_SEL_A, value);

			elif regsel == DUART.REG_SEL_B:
				value = self._b.access(mode, addr - DUART.REG_SEL_B, value);

			elif addr == DUART.REG_IPCR:
				value = 0x03	# CTSA/CTSB are always asserted

			elif addr == DUART.REG_ISR:
				value = self._isr

			elif addr == DUART.REG_CUR:
				value = self._count >> 8

			elif addr == DUART.REG_CLR:
				value = self._count & 0xff

			elif addr == DUART.REG_IVR:
				value = self._ivr

			elif addr == DUART.REG_IPR:
				value = 0x03	# CTSA/CTSB are always asserted

			elif addr == DUART.REG_STARTCC:
				self._count = self._countReload

			elif addr == DUART.REG_STOPCC:
				pass

			else:
				value = 0xff

			regname = self.get_register_name(addr).split('/')[0]
			self.trace('{} -> 0x{:02x}'.format(regname, value))

		elif mode == device.MODE_WRITE:
			regname = self.get_register_name(addr).split('/')[-1]
			self.trace('{} <- 0x{:02x}'.format(regname, value))

			regsel = addr & DUART.REG_SELMASK
			if regsel == DUART.REG_SEL_A:
				self._a.access(mode, addr - DUART.REG_SEL_A, value);

			elif regsel == DUART.REG_SEL_B:
				self._b.access(mode, addr - DUART.REG_SEL_B, value);

			elif addr == DUART.REG_ACR:
				self._acr = value

			elif addr == DUART.REG_IMR:
				self._imr = value
				# XXX interrupt status may have changed...

			elif addr == DUART.REG_CTUR:
				self._countReload = (value << 8) + (self._countReload & 0xff)

			elif addr == DUART.REG_CTLR:
				self._countReload = (self._countReload & 0xff00) + value

			elif addr == DUART.REG_IVR:
				self._ivr = value

			#elif addr == DUART.REG_OPCR:
			#elif addr == DUART.REG_OPRSET:
			#elif addr == DUART.REG_OPRCLR:
			pass

		return value

	def tick(self, current_time):
		pass

	def reset(self):
		self._a.reset()
		self._b.reset()
		self._isr = 0
		self._imr = 0
		self._ivr = 0xf
		self._count = 0
		self._countReload = 0xffff
		self._acr = DUART.ACR_MODE_TMR_XTAL


	def get_vector(self, interrupt):
		pass
