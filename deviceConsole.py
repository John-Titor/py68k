import sys
import curses
from device import device

class Console(device):

	stdscr = None

	# VT100 and a smattering of later DEC encodings
	input_keymap = {
		10			: '\x0d',	# nl -> enter
		127			: '\x08',	# del -> bs
		curses.KEY_DOWN		: '\x1bB',	# Down-arrow
		curses.KEY_UP		: '\x1bA',	# Up-arrow
		curses.KEY_LEFT		: '\x1bD',	# Left-arrow
		curses.KEY_RIGHT	: '\x1bC',	# Right-arrow
		curses.KEY_HOME		: '\x1b1',	# Home key (upward+left arrow)
		curses.KEY_F0		: '\x1bOP',	# Function keys. Up to 64 function keys are supported.
		curses.KEY_F1		: '\x1bOQ',	# Function keys. Up to 64 function keys are supported.
		curses.KEY_F2		: '\x1bOR',	# Function keys. Up to 64 function keys are supported.
		curses.KEY_F3		: '\x1bOS',	# Function keys. Up to 64 function keys are supported.
		curses.KEY_DC		: '\x08',	# Delete character
		curses.KEY_IC		: '\x1b2',	# Insert char or enter insert mode
		curses.KEY_NPAGE	: '\x1b6',	# Next page
		curses.KEY_PPAGE	: '\x1b5',	# Previous page
		curses.KEY_END		: '\x1b4'	# End
	}

	def __init__(self, args, address, interrupt, debug = False):
		super(Console, self).__init__('console', debug = debug)
		device.root_device.register_console_output_driver(self)
		Console.stdscr.nodelay(1)
		Console.stdscr.scrollok(1)
		Console.stdscr.idlok(1)

	def _fmt(self, val):
		str = '{}'.format(val)
		# XXX need to handle this better, maybe curses can help?
		try:
			ch = chr(val)
			if ch.isalnum():
				str += ' \'{}\''.format(ch)
		except:
			pass
		return str

	def _handle_input(self, input):
		self.trace('in ' + self._fmt(input))
		device.root_device.console_input(input)

	def handle_console_output(self, output):
		self.trace('out ' + self._fmt(output))
		Console.stdscr.echochar(chr(output))

	def tick(self):
		Console.stdscr.refresh()
		input = Console.stdscr.getch()
		if input != -1:

			if input in Console.input_keymap:
				self.trace('translate {} -> {}'.format(input, Console.input_keymap[input]))
				for c in Console.input_keymap[input]:
					self._handle_input(ord(c))
			else:
				self._handle_input(input)
