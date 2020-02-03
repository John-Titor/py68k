import sys
import os
import socket
import selectors

from musashi.m68k import (
    # Musashi API
    M68K_REG_SR,
    M68K_IRQ_SPURIOUS,
    M68K_IRQ_AUTOVECTOR,

    set_int_ack_callback,
    set_irq,
    get_reg,

    # Memory API
    MEM_PAGE_MASK,
    MEM_READ,
    MEM_WRITE,
    MEM_WIDTH_8,
    MEM_WIDTH_16,
    MEM_WIDTH_32,

    mem_add_device,
    mem_set_device_handler,
)


class Device(object):
    """
    Generic device model.

    Device models should:

    - call super().__init__(args, name, [address], [interrupt])
    - if they supplied an address, implement read() and write()
    - if they supplied an interrupt, implement get_interrupt() and get_vector()
    - if they need to do periodic work, implement tick()
    - if they need to do work on a reset instruction, implement reset()

    """
    _register_to_device = dict()
    _devices = list()
    _emu = None
    _debug = False

    _root_device = None

    _console_output_handler = None
    _console_input_handler = None

    WIDTH_8 = MEM_WIDTH_8
    WIDTH_16 = MEM_WIDTH_16
    WIDTH_32 = MEM_WIDTH_32

    def __init__(self, args, name, address=None, interrupt=None):
        self._name = name
        self._address = address
        self._size = 0
        self._interrupt = interrupt

        self._debug = self._name in args.debug_device

    @classmethod
    def add_arguments(cls, parser):
        """Common arguments applying to all devices"""
        parser.add_argument('--debug-device',
                            action='append',
                            metavar='DEVICE-NAME',
                            help='enable debugging for DEVICE-NAME, \'Device\''
                            ' to trace device framework.')

    def map_registers(self, registers):
        """
        Map device registers
        """
        if self._address is None:
            raise RuntimeError('cannot map registers without base address')
        self._register_name_map = {}
        for reg in registers:
            regaddr = self._address + registers[reg]
            if (regaddr in Device._register_to_device):
                other = Device._register_to_device[regaddr]
                if self != other:
                    raise RuntimeError(f'register at 0x{regaddr:x} already assigned to {other._name}')
            Device._register_to_device[regaddr] = self
            self._register_name_map[registers[reg]] = reg
            # round up to next word address
            if registers[reg] >= self._size:
                self._size = (registers[reg] + MEM_PAGE_MASK) & ~MEM_PAGE_MASK

            if self._debug:
                Device._emu.trace('DEVICE', address=regaddr,
                                  info=f'add register {reg}/0x{registers[reg]:x} for {self._name}')

    def trace(self, action, info=''):
        """
        Emit a debug trace message
        """
        if self._debug:
            Device._emu.trace('DEVICE', info='{}: {} {}'.format(
                self._name, action, info))

    def get_register_name(self, offset):
        if offset in self._register_name_map:
            return self._register_name_map[offset]
        else:
            return f'???@0x{offset:x}'

    @classmethod
    def register_console_output_handler(cls, handler):
        Device._console_output_handler = handler

    @classmethod
    def register_console_input_handler(cls, handler):
        Device._console_input_handler = handler

    @classmethod
    def console_handle_output(cls, output):
        if Device._console_output_handler is not None:
            Device._console_output_handler(output)

    @classmethod
    def console_handle_input(cls, input):
        if Device._console_input_handler is not None:
            Device._console_input_handler(input)

    @property
    def current_time(self):
        return self._root_device._emu.current_time

    @property
    def current_cycle(self):
        return self._root_device._emu.current_cycle

    @property
    def cycle_rate(self):
        return self._root_device._emu.cycle_rate

    @property
    def address(self):
        return self._address

    @property
    def size(self):
        return self._size

    #
    # Methods that should be implemented by device models
    #

    def read(self, width, offset):
        """
        Called when a CPU read access decodes to one of the registers defined in a call to map_registers.
        width is one of Device.WIDTH_8, Device.WIDTH_16 or Device.WIDTH_32
        offset is the register offset from the device base address
        Function should return the read value.
        """
        return 0

    def write(self, width, offset, value):
        """
        Called when a CPU write access decodes to one of the registers defined in a call to map_registers.
        width is one of Device.WIDTH_8, Device.WIDTH_16 or Device.WIDTH_32
        offset is the register offset from the device base address
        value is the value being written
        """
        pass

    def tick(self):
        """
        Called every emulator tick
        """
        return 0

    def reset(self):
        """
        Called at emulator reset time
        """
        return

    def get_interrupt(self):
        """
        Called to determine whether the device is interrupting; should return the device
        IPL if interrupting or 0 if not.
        """
        return 0

    def get_vector(self, interrupt):
        """
        Called during the interrupt acknowledge phase. Should return a programmed vector or
        M68K_IRQ_AUTOVECTOR as appropriate if the device is interrupting, or M68K_IRQ_SPURIOUS
        otherwise.
        """
        return M68K_IRQ_SPURIOUS


class RootDevice(Device):

    def __init__(self, args, emu):
        super(RootDevice, self).__init__(args=args, name='root')
        Device._emu = emu
        Device._root_device = self

        Device._debug = 'device' in args.debug_device

        self._trace_io = args.trace_io or args.trace_everything

        set_int_ack_callback(self.cb_int)
        mem_set_device_handler(self.cb_access)

        emu.add_reset_hook(self.reset)

    def add_system_devices(self, args):
        if args.stdout_console:
            Device._emu.add_device(args, StdoutConsole)
        else:
            Device._emu.add_device(args, SocketConsole)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--stdout-console',
                            action='store_true',
                            default=False,
                            help='sends console output to stdout instead of connecting '
                            'to the console server. Disconnects console input.')
        parser.add_argument('--trace-io',
                            action='store_true',
                            help='enable tracing of I/O space accesses')
        # StdoutConsole.add_arguments(parser)
        # SocketConsole.add_arguments(parser)

    def cb_int(self, interrupt):
        try:
            for dev in Device._devices:
                vector = dev.get_vector(interrupt)
                if vector != M68K_IRQ_SPURIOUS:
                    self.trace(f'{dev._name} returns vector {vector:#x}')
                    return vector
            self.trace('no interrupting device')
        except Exception:
            self._emu.fatal_exception(sys.exc_info())

        return M68K_IRQ_SPURIOUS

    def cb_access(self, operation, address, width, value):
        try:
            # look for a device
            try:
                dev = Device._register_to_device[address]
            except KeyError:
                self.trace('lookup', f'failed to find device to handle access @{address:#x}')
                return 0

            # dispatch to device emulator
            offset = address - dev._address
            if operation == MEM_READ:
                value = dev.read(width, offset)

                if self._trace_io:
                    label = f'{dev._name}:{dev.get_register_name(offset).split("/")[0]}'
                    if width == Device.WIDTH_8:
                        str = f'{label} -> {value:#02x}'
                    elif width == Device.WIDTH_16:
                        str = f'{label} -> {value:#04x}'
                    else:
                        str = f'{label} -> {value:#08x}'
                    Device._emu.trace('DEV_READ', address=address, info=str)

            elif operation == MEM_WRITE:
                if self._trace_io:
                    label = f'{dev._name}:{dev.get_register_name(offset).split("/")[-1]}'
                    if width == Device.WIDTH_8:
                        str = f'{label} <- {value:#02x}'
                    elif width == Device.WIDTH_16:
                        str = f'{label} <- {value:#04x}'
                    else:
                        str = f'{label} <- {value:#08x}'
                    Device._emu.trace('DEV_WRITE', address=address, info=str)

                dev.write(width, offset, value)
            else:
                raise RuntimeError(f'impossible device access {operation}')

            self.check_interrupts()

        except Exception as e:
            self._emu.fatal_exception(sys.exc_info())

        return value

    def add_device(self, args, dev, address=None, interrupt=None):
        new_dev = dev(args=args, address=address, interrupt=interrupt)
        if address is not None:
            if not mem_add_device(address, new_dev.size):
                raise RuntimeError(f"could not map device @ 0x{address:x}/{size}")
        Device._devices.append(new_dev)

    def tick(self):
        self.trace('DEV', info='TICK')
        deadline = None
        for dev in Device._devices:
            ret = dev.tick()
            # let the device request an earlier deadline
            if ret is not None:
                ret = int(ret)
                if ret > 0:
                    if deadline is None or ret < deadline:
                        deadline = ret

        self.check_interrupts()
        return deadline

    def reset(self, emu):
        for dev in Device._devices:
            dev.reset()

    def check_interrupts(self):
        ipl = 0
        for dev in Device._devices:
            dev_ipl = dev.get_interrupt()
            if dev_ipl > ipl:
                interruptingDevice = dev
                ipl = dev_ipl
        if ipl > 0:
            SR = get_reg(M68K_REG_SR)
            cpl = (SR >> 8) & 7
            if ipl > cpl:
                self.trace(f'{interruptingDevice._name} asserts ipl {ipl}')
        set_irq(ipl)


class SocketConsole(Device):
    def __init__(self, args, address, interrupt):
        super(SocketConsole, self).__init__(args=args, name='console')

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._socket.connect(('localhost', 6809))
            self._selector = selectors.DefaultSelector()
            self._selector.register(self._socket,
                                    selectors.EVENT_READ,
                                    self._recv)
        except ConnectionRefusedError as e:
            self._emu.fatal('console server not listening, run \'py68k.py --console-server\' in another window.')

        Device.register_console_output_handler(self._send)

    def _send(self, output):
        self._socket.send(output)

    def tick(self):
        events = self._selector.select(timeout=0)
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)

    def _recv(self, conn, mask):
        input = conn.recv(10)
        if len(input) == 0:
            self._emu.fatal('console server disconnected')
        Device.console_handle_input(input)


class StdoutConsole(Device):
    def __init__(self, args, address, interrupt):
        super(StdoutConsole, self).__init__(args=args, name='console')
        Device.register_console_output_handler(self._send)

    def _send(self, output):
        sys.stdout.write(output.decode('latin-1'))
        sys.stdout.flush()
