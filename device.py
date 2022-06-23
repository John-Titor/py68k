#
# Base device model
#

import sys

from musashi import m68k
from register import Register
from trace import Trace


class Device(object):
    """
    Generic device model.
    """
    __devices = list()
    __callbacks = dict()

    __emu = None
    __root_device = None
    __debug = False
    __trace = None

    __console_output_handler = None
    __console_input_handler = None

    def __init__(self, args, name, required_options=None, **options):
        self.name = name
        if Device.__trace is None:
            Device.__trace = Trace.get_tracer()

        if required_options is not None:
            for optname in required_options:
                if optname not in options:
                    raise RuntimeError(f'{self.name} missing required option {optname}')

        # handle some common options
        self.address = options['address'] if 'address' in options else None
        self.interrupt = options['interrupt'] if 'interrupt' in options else None
        self.size = None
        self.debug = self.name in args.debug_device
        self._asserted_ipl = 0

    @classmethod
    def add_global_arguments(cls, parser):
        """Common arguments applying to all devices"""
        parser.add_argument('--debug-device',
                            action='append',
                            default=list(),
                            metavar='DEVICE-NAME',
                            help='enable debugging for DEVICE-NAME, \'Device\''
                            ' to trace device framework.')
        Register.add_arguments(parser)

    @classmethod
    def add_arguments(cls, parser):
        pass

    ########################################
    # Devices

    @classmethod
    def add_device(cls, args, dev, **options):

        if Device.__root_device is None:
            # one-time init
            Register.init(args)
            m68k.set_int_ack_callback(Device.__cb_int)
            m68k.mem_set_device_handler(Device.__cb_access)
            Device.__debug = 'Device' in args.debug_device
            Device.__emu = options['emulator']

            Device.__root_device = dev(args=args, **options)
            Device.__root_device.add_system_devices(args)
        else:
            new_dev = dev(args=args, **options)
            Device.__devices.append(new_dev)

    @classmethod
    def find_device(cls, name):
        for dev in Device.__devices:
            if dev.name == name:
                return dev

    @classmethod
    def cb_reset(cls):
        for dev in Device.__devices:
            try:
                dev.reset()
            except Exception as e:
                Device.__emu.fatal_exception(sys.exc_info())
                break

    ########################################
    # Registers

    def add_register(self, name, offset, size, access, handler):
        """
        add a register to be handled by the device
        """
        reg = Register(self, name, offset, size, access, handler)
        implied_size = int(offset + (size / 8))
        if self.size is None:
            self.size = implied_size
        elif implied_size > self.size:
            self.size = implied_size

        if self.debug or self.__class__.__debug:
            Device.trace(action='MAP_REG',
                         address=reg.address,
                         info=f'{reg}:{Trace.operation_map[access]}:{size}')

    def add_registers(self, registers):
        """
        add registers in bulk
        """
        for name, offset, size, access, handler in registers:
            self.add_register(name, offset, size, access, handler)

    @classmethod
    def __cb_access(cls, operation, address, size, value):
        # check for a register operation
        try:
            return Register.access(address, size, operation, value)
        except KeyError:
            pass
        except Exception:
            Device.__emu.fatal_exception(sys.exc_info())

        # check for a mapped aperture
        try:
            return Device.__access(address, size, operation, value)
        except KeyError:
            # XXX bus error?
            Device.trace(action='DECODE',
                         address=address,
                         info=f'no register to handle {Trace.operation_map[operation]}:{size}')
        except Exception:
            Device.__emu.fatal_exception(sys.exc_info())

        # nothing handling this operation
        return -1

    @classmethod
    def __access(cls, address, size, operation, value):
        for dev in cls.__devices:
            try:
                if (((dev.address is not None)
                     and (address >= dev.address)
                     and (address < (dev.address + dev.size)))):
                    return dev.access(address - dev.address, size, operation, value)
            except AttributeError:
                continue
        raise KeyError()

    ########################################
    # Device callbacks

    def callback_at(self, cb_at, cb_name, cb_func):
        """
        arrange for cb_func to be called once the total elapsed cycles passes cb_at
        """
        cb_at = int(cb_at)
        if cb_at <= self.current_cycle:
            raise RuntimeError(f'{self.name} attempt to register callback in the past')
        else:
            self.trace(info=f'set callback \'{cb_name}\' at {cb_at}')
        self.__add_callback(self, cb_at, cb_name, cb_func)

    def callback_after(self, cb_after, cb_name, cb_func):
        """
        arrange for cb_func to be called after cb_after cycles have elapsed
        """
        self.callback_at(self.current_cycle + cb_after, cb_name, cb_func)

    def callback_every(self, cb_period, cb_name, cb_func):
        """
        arrange for cb_func to be called every cb_period cycles
        """
        self.__add_callback(self, self.current_cycle + cp_period, cb_name, cb_func, cb_period)

    def callback_cancel(self, cb_name):
        """
        cancel the callback cb_name for this device
        """
        self.__remove_callback(self, cb_name)

    @classmethod
    def __add_callback(cls, cb_dev, cb_at, cb_name, cb_func, cb_period=None):
        Device.__callbacks[(cb_dev, cb_name)] = {
            'cycle': cb_at,
            'func': cb_func,
            'period': cb_period,
        }
        Device.__set_callback()

    @classmethod
    def __remove_callback(cls, cb_dev, cb_name):
        Device.__callbacks.pop((cb_dev, cb_name), None)
        Device.__set_callback()

    @classmethod
    def __set_callback(cls):
        """
        Arrange to be called back at the earliest future deadline.
        """
        earliest = sys.maxsize
        earliest_handle = None
        for ident, info in Device.__callbacks.items():
            cycle = info['cycle']
            if (cycle > Device.__emu.current_cycle) and (cycle < earliest):
                earliest = cycle
                _, earliest_handle = ident
        if earliest < sys.maxsize:
            Device.__emu.set_device_callback(earliest, Device.__callback)

    @classmethod
    def __callback(cls):
        """
        invoke every callback that's due
        """
        ident_list = list(Device.__callbacks.keys())
        for ident in ident_list:
            info = Device.__callbacks[ident]
            if info['cycle'] <= Device.__emu.current_cycle:
                _, handle = ident
                func = info['func']
                if info['period'] is not None:
                    info['cycle'] += info['period']
                    Device.__callbacks[ident] = info
                else:
                    Device.__callbacks.pop(ident, False)
                func()

        Device.__set_callback()

    ########################################
    # Interrupts

    def assert_ipl(self, ipl=None):
        if ipl is None:
            if self.interrupt is None:
                raise RuntimeError(f'{self.name} was not assigned an interrupt')
            ipl = self.interrupt
        self._asserted_ipl = ipl
        self.trace(info=f'asserted IPL {ipl}')
        self.__set_ipl()

    def deassert_ipl(self):
        self.assert_ipl(0)

    @property
    def ipl_asserted(self):
        return self._asserted_ipl > 0

    @classmethod
    def __set_ipl(cls):
        ipl = 0
        asserting_dev = None
        for dev in Device.__devices:
            if dev._asserted_ipl > ipl:
                ipl = dev._asserted_ipl
                asserting_dev = dev
        if ipl > 0:
            SR = m68k.get_reg(m68k.REG_SR)
            cpl = (SR >> 8) & 7
            if ipl > cpl:
                # emulator only checks for interrupts at the start of a timeslice
                # or when SR is changed by the program, so if we have just asserted
                # an unmasked interrupt we need to end the timeslice to get its
                # attention
                m68k.end_timeslice()
                Device.trace(info=f'un-masked IPL {ipl} from {asserting_dev.name}')
            else:
                Device.trace(info=f'masked IPL {ipl} from {asserting_dev.name}')
        m68k.set_irq(ipl)

    @classmethod
    def __cb_int(cls, interrupt):
        """
        run an interrupt-acknowledge cycle for the given interrupt
        """
        for dev in Device.__devices:
            if dev._asserted_ipl == interrupt:
                vector = dev.get_vector(interrupt)
                if vector != m68k.IRQ_SPURIOUS:
                    Device.trace(info=f'INTERRUPT, vector {vector}')
                    return vector
        Device.trace(info='SPURIOUS_INTERRUPT')
        return m68k.IRQ_SPURIOUS

    ########################################
    # Console

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

    ########################################
    # Time

    @property
    def current_time(self):
        """
        get the current time in microseconds
        """
        return self.emu.current_time

    @property
    def current_cycle(self):
        """
        get the current time in CPU cycles
        """
        return self.emu.current_cycle

    @property
    def cycle_rate(self):
        """
        get the CPU cycle rate in Hz
        """
        return self.emu.cycle_rate

    ########################################
    # Properties

    @property
    def emu(self):
        return self.__class__.__emu

    @property
    def root_device(self):
        return self.__class__.__root_device

    @property
    def devices(self):
        return self.__class__.__devices

    ########################################
    # Tracing

    def trace(self, address=None, info=''):
        if self.debug:
            Device.__trace.trace(action=self.name, address=address, info=info)

    @classmethod
    def trace(cls, action='', address=None, info=''):
        if cls.__debug:
            cls.__trace.trace(action=action, address=address, info=info)

    ########################################
    # Subclass protocol

    def reset(self):
        """
        Called at emulator reset time
        """
        return

    def get_vector(self, interrupt):
        """
        Called during the interrupt acknowledge phase. If the interrupt argument matches the
        device IPL, should return a programmed vector or m68k.IRQ_AUTOVECTOR as appropriate if
        the device is interrupting, or m68k.IRQ_SPURIOUS otherwise.
        """
        return m68k.IRQ_SPURIOUS
