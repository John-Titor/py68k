#
# Device register emulation
#

import sys

from musashi import m68k
from trace import Trace


class Register:
    __registers = dict()
    __trace = None

    def __init__(self, dev, name, offset, size, access, handler):
        if Register.__trace is None:
            raise RuntimeError('cannot define register without trace')
        self.dev = dev
        self.name = name
        self.address = dev.address + offset
        self.size = size
        self.access = access
        self._handler = handler

        # validate alignment
        if size == m68k.MEM_SIZE_8:
            pass
        elif (size == m68k.MEM_SIZE_16):
            if (self.address & 1) != 0:
                raise RuntimeError(f'{self} not 2-aligned')
        elif (size == m68k.MEM_SIZE_32):
            if (self.address & 3) != 0:
                raise RuntimeError(f'{self} not 4-aligned')

        if size not in [m68k.MEM_SIZE_8, m68k.MEM_SIZE_16, m68k.MEM_SIZE_32]:
            raise RuntimeError(f'{self} has unrecogized size')
        if access not in [m68k.MEM_READ, m68k.MEM_WRITE]:
            raise RuntimeError(f'{self} has unrecognized access')

        # validate uniqueness
        try:
            conflicting_reg = Register.lookup(address=self.address, size=self.size, access=self.access)
            raise RuntimeError(f'register {self} conflicts with {conflicting_reg}')
        except KeyError:
            pass

        # save for use later
        Register.__registers[self.key] = self

    @classmethod
    def init(cls, args):
        Register.__trace = Trace.get_tracer()
        Register.__trace_io = args.trace_io or args.trace_everything

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('--trace-io',
                            action='store_true',
                            help='enable tracing of all device register accesses')

    def _access(self, value=None):
        """
        handle an access to the register
        """
        if self.access == m68k.MEM_READ:
            value = self._handler()
            self.trace_io(value)
            return value
        elif self.access == m68k.MEM_WRITE:
            if value is None:
                raise RuntimeError(f'cannot write {self} without value')
            self.trace_io(value)
            self._handler(value)
            return 0
        else:
            raise RuntimeError(f'{self} not accessible')

    def __repr__(self):
        if self.access == m68k.MEM_READ:
            direction = 'R'
        elif self.access == m68k.MEM_WRITE:
            direction = 'W'
        return f'{self.dev.name}.{self.name}'
        # return f'{direction}:{self.dev.name}.{self.name}@{self.address:#x}/{self.size}'

    def trace_io(self, value):
        if Register.__trace_io or self.dev.debug:
            if self.access == m68k.MEM_READ:
                arrow = '->'
                action = 'DEV_READ'
            else:
                arrow = '<-'
                action = 'DEV_WRITE'

            if self.size == m68k.MEM_SIZE_8:
                xfer = f'{arrow} {value:#02x}'
            elif self.size == m68k.MEM_SIZE_16:
                xfer = f'{arrow} {value:#04x}'
            else:
                xfer = f'{arrow} {value:#08x}'

            Register.__trace.trace(action=action, address=self.address, info=f'{self} {xfer}')

    @property
    def key(self):
        return (self.address, self.size, self.access)

    @classmethod
    def lookup(cls, address, size, access):
        return Register.__registers[(address, size, access)]

    @classmethod
    def access(cls, address, size, access, value=None):
        # XXX we could be smarter here and handle e.g. 16-bit access
        #     on top of an 8-bit or 32-bit register, etc.
        return Register.lookup(address, size, access)._access(value)

    @classmethod
    def dump_registers(cls):
        for reg in Register.__registers.values():
            print(f'{reg}')
