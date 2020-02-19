#
# Emulator-specific pseudo-devices
#

import os
import selectors
import socket
import sys

from device import Device
from musashi import m68k


class RootDevice(Device):

    def __init__(self, args, **options):
        super().__init__(args=args, name='root')
        self.emu.add_reset_hook(self.reset)

    def add_system_devices(self, args):
        if args.stdout_console:
            self.emu.add_device(args, StdoutConsole)
        else:
            self.emu.add_device(args, SocketConsole)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--stdout-console',
                            action='store_true',
                            default=False,
                            help='sends console output to stdout instead of connecting '
                            'to the console server. Disconnects console input.')
        # StdoutConsole.add_arguments(parser)
        # SocketConsole.add_arguments(parser)


class SocketConsole(Device):
    def __init__(self, args, **options):
        super().__init__(args=args, name='console')

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.connect(('localhost', 6809))
            self._selector = selectors.DefaultSelector()
            self._selector.register(self._socket,
                                    selectors.EVENT_READ,
                                    self._recv)
        except ConnectionRefusedError as e:
            self.emu.fatal('console server not listening, run \'py68k.py --console-server\' in another window.')

        super().register_console_output_handler(self._send)
        self.callback_after(self.cycle_rate / 100, 'console', self._check_socket)

    def _send(self, output):
        self._socket.send(output)

    def _check_socket(self):
        events = self._selector.select(timeout=0)
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)
        self.callback_after(self.cycle_rate / 100, 'console', self._check_socket)

    def _recv(self, conn, mask):
        input = conn.recv(10)
        if len(input) == 0:
            self.emu.fatal('console server disconnected')
        super().console_handle_input(input)


class StdoutConsole(Device):
    def __init__(self, args, address, interrupt):
        super().__init__(args=args, name='console')
        super().register_console_output_handler(self._send)

    def _send(self, output):
        sys.stdout.write(output.decode('latin-1'))
        sys.stdout.flush()
