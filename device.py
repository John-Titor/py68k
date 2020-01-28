import sys
import os
import socket

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
    DEV_READ,
    DEV_WRITE,
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

    _console_output_handler = None

    RootDevice = None

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
                            type=str,
                            default='',
                            help='comma-separated list of devices to enable debug tracing, \'device\''
                            ' to trace device framework')

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

    def console_write(self, output):
        if Device._console_output_handler is not None:
            Device._console_output_handler(output)

    @property
    def current_time(self):
        return self.RootDevice._emu.current_time

    @property
    def current_cycle(self):
        return self.RootDevice._emu.current_cycle

    @property
    def cycle_rate(self):
        return self.RootDevice._emu.cycle_rate

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

    def get_vector(self):
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
        Device.RootDevice = self

        Device._debug = 'device' in args.debug_device

        self._trace_io = args.trace_io or args.trace_everything

        set_int_ack_callback(self.cb_int)
        mem_set_device_handler(self.cb_access)

        emu.add_reset_hook(self.reset)

        self._console_socket = None
        self._console_in_fd = 0
        self._console_out_fd = 1
        if args.console_port is not None:
            self._console_socket = socket(AF_INET, SOCK_STREAM)
            try:
                self._console_socket.connect(('localhost', args.console_port))
                self._console_in_fd = self._console_socket.fileno()
                self._console_out_fd = self._console_socket.fileno()
            except ConnectionRefusedError as e:
                print(f'\nconsole server not listening, try \'nc -4lk localhost {args.console_port}\'\n')
                raise

        Device._console_output_handler = self._console_output

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--console-port',
                            type=int,
                            choices=range(1025, 65535),
                            metavar='PORT-NUMBER',
                            help='connects the console to a TCP server listening on localhost:PORT-NUMBER')

    def cb_int(self, interrupt):
        try:
            for dev in Device._devices:
                vector = dev.get_vector(interrupt)
                if vector != M68K_IRQ_SPURIOUS:
                    self.trace('{} returns vector 0x{:x}'.format(
                        dev._name, vector))
                    return vector
            self.trace('no interrupting device')
        except Exception:
            self._emu.fatal_exception(sys.exc_info())

        return M68K_IRQ_SPURIOUS

    def cb_access(self, operation, handle, offset, width, value):
        address = handle + offset
        try:
            # look for a device
            if address not in Device._register_to_device:
                self.trace('lookup', 'failed to find device to handle access')
                Device._emu.cb_buserror(mode, width, address)
                return 0

            # dispatch to device emulator
            dev = Device._register_to_device[address]
            offset = address - dev._address
            if operation == DEV_READ:
                value = dev.read(width, offset)

                if self._trace_io:
                    label = "{}:{}".format(
                        dev._name, dev.get_register_name(offset).split('/')[0])
                    if width == Device.WIDTH_8:
                        str = '{} -> 0x{:02x}'.format(label, value)
                    elif width == Device.WIDTH_16:
                        str = '{} -> 0x{:04x}'.format(label, value)
                    else:
                        str = '{} -> 0x{:08x}'.format(label, value)
                    Device._emu.trace('DEV_READ', address=address, info=str)

            else:
                if self._trace_io:
                    label = "{}:{}".format(dev._name, dev.get_register_name(offset).split('/')[-1])
                    if width == Device.WIDTH_8:
                        str = '{} <- 0x{:02x}'.format(label, value)
                    elif width == Device.WIDTH_16:
                        str = '{} <- 0x{:04x}'.format(label, value)
                    else:
                        str = '{} <- 0x{:08x}'.format(label, value)
                    Device._emu.trace('DEV_WRITE', address=address, info=str)

                dev.write(width, offset, value)

            self.check_interrupts()

        except Exception as e:
            self._emu.fatal_exception(sys.exc_info())

        return value

    def add_device(self, args, dev, address=None, interrupt=None):
        new_dev = dev(args=args, address=address, interrupt=interrupt)
        if address is not None:
            if not mem_add_device(address, new_dev.size, new_dev.address):
                raise RuntimeError(f"could not map device @ 0x{address:x}/{size}")
        Device._devices.append(new_dev)

    def tick(self):
        deadline = 100000
        for dev in Device._devices:
            ret = dev.tick()
            # let the device request an earlier deadline
            if ret is not None:
                ret = int(ret)
                if ret > 0 and ret < deadline:
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
                self.trace('{} asserts ipl {}'.format(
                    interruptingDevice._name, ipl))
        set_irq(ipl)

    def console_input(self, input):
        # XXX
        return None

    def _console_output(self, output):
        if self._console_out_fd is not None:
            os.write(self._console_out_fd, output)

# XXX these are horribly outdated right now...


class uart(Device):
    """
    Dumb UART
    """

    _registers = {
        'SR': 0x00,
        'DR': 0x02
    }
    SR_RXRDY = 0x01
    SR_TXRDY = 0x02

    def __init__(self, args, base, interrupt):
        super(uart, self).__init__(args=args, name='uart',
                                   address=base, interrupt=interrupt)
        self.map_registers(self._registers)
        self.reset()

    def read(self, width, addr):
        if addr == self._registers['SR']:
            value = 0
            if self._rx_ready:
                value |= SR_RXRDY
            if self._tx_ready:
                value |= SR_TXRDY
        elif addr == self._registers['DR']:
            value = self._rx_data

        return value

    def write(self, width, addr, value):
        if addr == self._registers['DR']:
            self.trace('write', '{}'.format(chr(value).__repr__()))
            sys.stdout.write(chr(value))
            sys.stdout.flush()

    def tick(self):
        # emulate tx drain, get rx data from stdin?
        return 0

    def reset(self):
        self._rx_ready = False
        self._tx_ready = True
        self._rx_data = 0

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS


class timer(Device):
    """
    A simple down-counting timer
    """

    _registers = {
        'RELOAD': 0x00,
        'COUNT': 0x04
    }

    def __init__(self, args, base, interrupt):
        super(timer, self).__init__(args=args, name='timer',
                                    address=base, interrupt=interrupt)
        self.map_registers(self._registers)
        self.reset()

    def read(self, width, addr):
        if addr == self._registers['RELOAD']:
            value = self._reload
        if addr == self._registers['COUNT']:
            # force a tick to make sure we have caught up with time
            self.tick(Device._emu.current_time)
            value = self._count
        return value

    def write(self, width, addr, value):
        if addr == self._registers['RELOAD']:
            self.trace('set reload', '{}'.format(value))
            self._reload = value
            self._count = self._reload
            self._last_update = Device._emu.current_time

    def tick(self):
        # do nothing if we are disabled
        if self._reload == 0:
            return 0

        # how much time has elapsed?
        current_time = self.current_time
        delta = (current_time - self._last_update) % self._reload
        self._last_update = current_time

        if self._count >= delta:
            # we are still counting towards zero
            self._count -= delta
        else:
            # we have wrapped, do reload & interrupt
            self.trace('tick', '')
            delta -= self._count
            self._count = self._reload - delta
            set_irq(self._interrupt)

        # send back a hint as to when we should be called again for best results
        return self._count

    def reset(self):
        self._reload = 0
        self._count = 0
        self._last_update = 0

    def get_vector(self, interrupt):
        if interrupt == self._interrupt:
            return M68K_IRQ_AUTOVECTOR
        return M68K_IRQ_SPURIOUS
