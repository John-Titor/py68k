import sys
from device import device

class Console(device):

	stdscr = None

	def __init__(self, address, interrupt, debug = False):
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

	def handle_console_output(self, output):
		self.trace('out ' + self._fmt(output))
		Console.stdscr.echochar(chr(output))

	def tick(self, current_time):
		Console.stdscr.refresh()
		input = Console.stdscr.getch()
		if input != -1:
			# we want CR, not NL
			if input == 10:
				input = 13
			self.trace('in ' + self._fmt(input))
			device.root_device.console_input(input)
