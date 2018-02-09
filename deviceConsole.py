import sys
from device import device

class Console(device):

	stdscr = None

	def __init__(self, address, interrupt, debug = False):
		super(Console, self).__init__('console', debug = debug)
		device.root_device.register_console_output_driver(self)

	def handle_console_output(self, output):
		self.trace('CONSOLE', info = '{} \'{}\''.format(output, chr(output)))
		Console.stdscr.addch(chr(output))
		Console.stdscr.refresh()
		#sys.stdout.write(chr(output))

