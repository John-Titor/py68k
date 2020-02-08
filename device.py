import sys
import os
import socket
import selectors

from musashi import m68k


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
    _register_map = dict()
    _devices = list()
    _emu = None
    _debug = False

    _root_device = None

    _console_output_handler = None
    _console_input_handler = None

    def __init__(self, args, name, required_options=None, **options):
        if required_options is not None:
            for optname in required_options:
                if optname not in options:
                    raise RuntimeError(f'required option {optname} not specified for {name}')
        self._name = name
        self._address = options['address'] if 'address' in options else None
        self._interrupt = options['interrupt'] if 'interrupt' in options else None
        self._size = 0
        self._debug = self._name in args.debug_device

        self.tick_deadline = 0

    @classmethod
    def add_arguments(cls, parser):
        """Common arguments applying to all devices"""
        parser.add_argument('--debug-device',
                            action='append',
                            default=list(),
                            metavar='DEVICE-NAME',
                            help='enable debugging for DEVICE-NAME, \'Device\''
                            ' to trace device framework.')

    def add_register(self, name, offset, size, read=None, write=None):
        """
        add a register to be handled by the device
        """
        register_address = self._address + offset
        if size == m68k.MEM_SIZE_8:
            pass
        elif (size == m68k.MEM_SIZE_16):
            if (register_address & 1) != 0:
                raise RuntimeError(f'register {name} size 16 at {register_address:#x} not 2-aligned')
        elif (size == m68k.MEM_SIZE_32):
            if (register_address & 3) != 0:
                raise RuntimeError(f'register {name} size 32 at {register_address:#x} not 4-aligned')
        Device._register_map[register_address] = {
            'device': self,
            'name': name,
            'size': size,
            'read': read,
            'write': write,
        }
        implied_size = int(offset + (size / 8))
        if implied_size > self._size:
            self._size = implied_size
        if self._debug:
            Device._emu.trace('MAP_REGISTER',
                              address=register_address,
                              info=f'{self._name}:{name} @ {register_address:#x}/{size}')

    def add_registers(self, registers):
        """
        add registers in bulk
        """
        for name, offset, size, read, write in registers:
            self.add_register(name, offset, size, read, write)

    def trace(self, action, info=''):
        """
        Emit a debug trace message
        """
        if self._debug:
            Device._emu.trace('DEVICE', info=f'{self._name}: {action} {info}')

    @classmethod
    def register_info(self, address):
        """
        get the info dictionary for the register at address
        """
        return Device._register_map[address]

    @classmethod
    def register_name(self, address):
        """
        get the pretty name for the register at address
        """
        try:
            reg_info = Device.register_info(address)
            dev_name = reg_info['device']._name
            name = f'{dev_name}.{reg_info["name"]}@{address:#x}/{reg_info["size"]}'
        except KeyError:
            name = f'???@{address:#x}'

        return name

    @classmethod
    def register_console_output_handler(cls, handler):
        """
        supply a handler for console output, will be called with a single byte at a time.
        """
        Device._console_output_handler = handler

    @classmethod
    def register_console_input_handler(cls, handler):
        """
        supply a handler for console input, may be called with multiple bytes
        """
        Device._console_input_handler = handler

    @classmethod
    def console_handle_output(cls, output):
        """
        send output to the console
        """
        if Device._console_output_handler is not None:
            Device._console_output_handler(output)

    @classmethod
    def console_handle_input(cls, input):
        """
        take input from the console
        """
        if Device._console_input_handler is not None:
            Device._console_input_handler(input)

    @property
    def current_time(self):
        """
        get the current time in microseconds
        """
        return self._root_device._emu.current_time

    @property
    def current_cycle(self):
        """
        get the current time in CPU cycles
        """
        return self._root_device._emu.current_cycle

    @property
    def cycle_rate(self):
        """
        get the CPU cycle rate in Hz
        """
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

    def tick(self):
        """
        Called after any register access, or when the emulator finishes a quantum.
        Driver may set the tick_deadline property, indicating a desire to be
        called again at or shortly after that cycle.
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
        Called during the interrupt acknowledge phase. If the interrupt argument matches the
        device IPL, should return a programmed vector or m68k.IRQ_AUTOVECTOR as appropriate if
        the device is interrupting, or m68k.IRQ_SPURIOUS otherwise.
        """
        return m68k.IRQ_SPURIOUS


class RootDevice(Device):

    def __init__(self, args, emu, **options):
        super(RootDevice, self).__init__(args=args, name='root')
        Device._emu = emu
        Device._root_device = self
        Device._debug = 'device' in args.debug_device

        self._trace_io = args.trace_io or args.trace_everything

        m68k.set_int_ack_callback(self.cb_int)
        m68k.mem_set_device_handler(self.cb_access)

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
                if vector != m68k.IRQ_SPURIOUS:
                    self.trace(f'{dev._name} returns vector {vector:#x}')
                    return vector
            self.trace('no interrupting device')
        except Exception:
            self._emu.fatal_exception(sys.exc_info())

        return m68k.IRQ_SPURIOUS

    def cb_access(self, operation, address, size, value):
        try:
            # look for a device
            try:
                reg_info = Device.register_info(address)
            except KeyError:
                self.trace('DECODE', f'no device handling {address:#x}/{size}')
                # XXX bus error?
                return 0xffffffff

            if operation == m68k.MEM_READ:
                handler_key = 'read'
            elif operation == m68k.MEM_WRITE:
                handler_key = 'write'
            else:
                raise RuntimeError(f'unexpected device access {operation}')

            handler = reg_info[handler_key]
            if handler is None:
                self.trace('DECODE', f'no handler {handler_key} for {Device.register_name(address)}')
                # XXX bus error?

            offset = address - reg_info['device']._address

            if operation == m68k.MEM_READ:
                value = handler()
                if self._trace_io:
                    label = f'{Device.register_name(address)}'
                    if size == m68k.MEM_SIZE_8:
                        str = f'{label} -> {value:#02x}'
                    elif size == m68k.MEM_SIZE_16:
                        str = f'{label} -> {value:#04x}'
                    else:
                        str = f'{label} -> {value:#08x}'
                    Device._emu.trace('DEV_READ', address=address, info=str)

            elif operation == m68k.MEM_WRITE:
                if self._trace_io:
                    label = f'{Device.register_name(address)}'
                    if size == m68k.MEM_SIZE_8:
                        str = f'{label} <- {value:#02x}'
                    elif size == m68k.MEM_SIZE_16:
                        str = f'{label} <- {value:#04x}'
                    else:
                        str = f'{label} <- {value:#08x}'
                    Device._emu.trace('DEV_WRITE', address=address, info=str)
                handler(value)

            self._check_interrupts()

        except Exception as e:
            self._emu.fatal_exception(sys.exc_info())

        return value

    def add_device(self, args, dev, **options):
        new_dev = dev(args=args, **options)
        if new_dev.address is not None:
            if not m68k.mem_add_device(new_dev.address, new_dev.size):
                raise RuntimeError(f"could not map device @ 0x{new_dev.address:x}/{new_dev.size}")
        Device._devices.append(new_dev)

    def tick_all(self):
        self.trace('DEV', info='TICK')
        for dev in Device._devices:
            dev.tick()
        self._check_interrupts()
        self._schedule_next_tick()

    def _tick_one(self, dev):
        dev.tick()
        self._check_interrupts()
        self._schedule_next_tick()

    def reset(self, emu):
        for dev in Device._devices:
            dev.reset()

    def _check_interrupts(self):
        ipl = 0
        for dev in Device._devices:
            dev_ipl = dev.get_interrupt()
            if dev_ipl > ipl:
                interruptingDevice = dev
                ipl = dev_ipl
        if ipl > 0:
            SR = m68k.get_reg(m68k.REG_SR)
            cpl = (SR >> 8) & 7
            if ipl > cpl:
                self.trace(f'{interruptingDevice._name} asserts ipl {ipl}')
                # emulator only checks for interrupts at the start of a timeslice
                # or when SR is changed by the program, so if we have just asserted
                # an unmasked interrupt we need to end the timeslice to get its
                # attention
                m68k.end_timeslice()
        m68k.set_irq(ipl)

    def _schedule_next_tick(self):
        earliest_deadline = sys.maxsize
        for dev in Device._devices:
            deadline_candidate = dev.tick_deadline
            if (deadline_candidate > 0) and (deadline_candidate < earliest_deadline):
                earliest_deadline = deadline_candidate
        self._emu.schedule_device_tick(earliest_deadline)


class SocketConsole(Device):
    def __init__(self, args, **options):
        super(SocketConsole, self).__init__(args=args, name='socket-console')

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
        return 0

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
