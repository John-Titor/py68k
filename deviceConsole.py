import sys
import curses
from device import device


class Console(device):

    stdscr = None

    # VT100 and a smattering of later DEC encodings
    input_keymap = {
        10 : '\x0d',
        127 : '\x08',
        curses.KEY_DOWN : '\x1bB',
        curses.KEY_UP : '\x1bA',
        curses.KEY_LEFT : '\x1bD',
        curses.KEY_RIGHT : '\x1bC',
        curses.KEY_HOME : '\x1b1',
        curses.KEY_F0 : '\x1bOP',
        curses.KEY_F1 : '\x1bOQ',
        curses.KEY_F2 : '\x1bOR',
        curses.KEY_F3 : '\x1bOS',
        curses.KEY_DC : '\x08',
        curses.KEY_IC : '\x1b2',
        curses.KEY_NPAGE : '\x1b6',
        curses.KEY_PPAGE : '\x1b5',
        curses.KEY_END : '\x1b4'
    }

    def __init__(self, args, address, interrupt, debug=False):
        super(Console, self).__init__('console', debug=debug)
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
                self.trace('translate {} -> {}'.format(input,
                                                       Console.input_keymap[input]))
                for c in Console.input_keymap[input]:
                    self._handle_input(ord(c))
            else:
                self._handle_input(input)
