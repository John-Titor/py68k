import sys
import curses
import vt102
from device import device


class Console(device):

    stdscr = None

    # VT100 and a smattering of later DEC encodings
    input_keymap = {
        127: '\x08',
        curses.KEY_DOWN: '\x1bB',
        curses.KEY_UP: '\x1bA',
        curses.KEY_LEFT: '\x1bD',
        curses.KEY_RIGHT: '\x1bC',
        curses.KEY_HOME: '\x1b1',
        curses.KEY_F0: '\x1bOP',
        curses.KEY_F1: '\x1bOQ',
        curses.KEY_F2: '\x1bOR',
        curses.KEY_F3: '\x1bOS',
        curses.KEY_DC: '\x08',
        curses.KEY_IC: '\x1b2',
        curses.KEY_NPAGE: '\x1b6',
        curses.KEY_PPAGE: '\x1b5',
        curses.KEY_END: '\x1b4'
    }

    def __init__(self, args, address, interrupt):
        super(Console, self).__init__(args=args, name='console')
        device.root_device.register_console_output_driver(self)
        curses.nonl()
        curses.curs_set(1)

        self._win = Console.stdscr
        self._win.nodelay(1)
        self._win.scrollok(0)
        self._win.idlok(1)

        self._vt_stream = vt102.stream()
        self._vt_screen = vt102.screen(self._win.getmaxyx())
        self._vt_screen.attach(self._vt_stream)
        self._buffered_output = u''

    def _fmt(self, val):
        str = '0x{:02x} \'{}\''.format(val, curses.keyname(val))
        return str

    def _handle_input(self, input):
        self.trace('in ' + self._fmt(input))
        device.root_device.console_input(input)

    def handle_console_output(self, output):
        self.trace('out ' + self._fmt(output))

        # vt102 is only 7-bit clean
        output &= 0x7f
        self._buffered_output += unichr(output)

    def tick(self):
        self._vt_stream.process(self._buffered_output)
        self._buffered_output = u''

        row = 0
        for str in self._vt_screen.display:
            try:
                self._win.addstr(row, 0, str)
            except:
                # XXX curses gets upset adding the last line - ignore it
                pass
            row += 1

        curs_x, curs_y = self._vt_screen.cursor()
        self._win.move(curs_y, curs_x)

        self._win.refresh()

        input = self._win.getch()
        if input != -1:

            if input in Console.input_keymap:
                self.trace('translate {} -> {}'.format(input,
                                                       Console.input_keymap[input]))
                for c in Console.input_keymap[input]:
                    self._handle_input(ord(c))
            else:
                self._handle_input(input)
