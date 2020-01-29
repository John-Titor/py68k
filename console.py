import sys
import os
import curses
import vt102
import socket
import selectors
import signal
import time


class Console():

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

    banner = '\n Waiting for emulator, hit ^C three times quickly to exit.\n'

    def __init__(self):
        self._selector = selectors.DefaultSelector()
        self._buffered_output = u''
        self._buffered_input = u''
        self._connection = None
        self._first_interrupt_time = 0.0
        self._interrupt_count = 0
        self._want_exit = False

    def run(self):
        signal.signal(signal.SIGINT, self._keyboard_interrupt)
        curses.wrapper(self._run)

    def _run(self, win):
        curses.nonl()
        curses.curs_set(1)

        self._win = win
        self._win.nodelay(1)
        self._win.scrollok(0)
        self._win.idlok(1)

        self._vt_stream = vt102.stream()
        self._vt_screen = vt102.screen(self._win.getmaxyx())
        self._vt_screen.attach(self._vt_stream)
        self._buffered_output = u''

        self._vt_stream.process(Console.banner)

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('127.0.0.1', 6809))
        server_socket.listen()
        server_socket.setblocking(False)
        self._selector.register(server_socket, selectors.EVENT_READ, self._accept)

        while True:
            events = self._selector.select(timeout=0.1)
            if self._want_exit:
                return
            for key, mask in events:
                callback = key.data
                callback(key.fileobj, mask)
            self._update()
            if len(self._buffered_input) > 0:
                if self._connection is not None:
                    self._connection.send(self._buffered_input.encode('ascii'))
                    self._buffered_input = u''

    def _accept(self, socket, mask):
        self._connection, _ = socket.accept()
        self._connection.setblocking(False)
        self._selector.register(self._connection, selectors.EVENT_READ, self._read)

    def _read(self, conn, mask):
        data = self._connection.recv(100)
        if data:
            for c in data:
                self._handle_output(c)
        else:
            # connection lost
            self._selector.unregister(self._connection)
            self._connection.close()
            self._connection = None
            self._vt_stream.process(Console.banner)

    def _fmt(self, val):
        str = f'{val:#02x} \'{curses.keyname(val)}\''
        return str

    def _handle_input(self, input):
        # self.trace('in ' + self._fmt(input))
        self._buffered_input += chr(input)

    def _handle_output(self, output):
        # self.trace('out ' + self._fmt(output))

        # vt102 is only 7-bit clean
        output &= 0x7f
        self._buffered_output += chr(output)

    def _update(self):
        self._vt_stream.process(self._buffered_output)
        self._buffered_output = u''

        row = 0
        for str in self._vt_screen.display:
            try:
                self._win.addstr(row, 0, str)
            except Exception:
                # XXX curses gets upset adding the last line - ignore it
                pass
            row += 1

        curs_x, curs_y = self._vt_screen.cursor()
        self._win.move(curs_y, curs_x)
        self._win.refresh()

        input = self._win.getch()
        if input != -1:
            if input in Console.input_keymap:
                # self.trace('translate {} -> {}'.format(input,
                #                                        Console.input_keymap[input]))
                for c in Console.input_keymap[input]:
                    self._handle_input(ord(c))
            else:
                self._handle_input(input)

    def _keyboard_interrupt(self, signal=None, frame=None):
        now = time.time()
        interval = now - self._first_interrupt_time

        if interval >= 1.0:
            self._first_interrupt_time = now
            self._interrupt_count = 1
        else:
            self._interrupt_count += 1
            if self._interrupt_count >= 3:
                self._want_exit = True
