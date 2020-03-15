import io
import struct
import sys
from collections import deque

from device import Device
from musashi import m68k


class UART(Device):
    """
    Simple UART
    """

    SR_RXRDY = 0x01
    SR_TXRDY = 0x02

    CR_RX_INTEN = 0x01
    CR_TX_INTEN = 0x02

    _unit = 0

    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='uart',
                         required_options=['address', 'interrupt'],
                         **options)
        self.add_registers([
            ('SR', 0x01, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_sr),
            ('DR', 0x03, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_dr),
            ('CR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cr),
            ('VR', 0x06, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_vr),

            ('DR', 0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_dr),
            ('CR', 0x05, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_cr),
            ('VR', 0x06, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_vr),
        ])
        self.reset()
        self._unit = UART._unit
        UART._unit += 1
        if self._unit == 0:
            self.register_console_input_handler(self._handle_console_input)

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_sr(self):
        value = UART.SR_TXRDY
        if len(self._rxfifo) > 0:
            value |= UART.SR_RXRDY
        return value

    def _read_dr(self):
        if len(self._rxfifo) > 0:
            return self._rxfifo.popleft()
            self._update_ipl()
        return 0

    def _write_dr(self, value):
        if self._unit == 0:
            self.console_handle_output(chr(value).encode('latin-1'))

    def _read_cr(self):
        return self._cr

    def _write_cr(self, value):
        self._cr = value
        self._update_ipl()

    def _read_vr(self):
        return self._vr

    def _write_vr(self, value):
        self._vr = value

    def reset(self):
        self._rxfifo = deque()
        self._vr = 0
        self._cr = 0

    def _update_ipl(self):
        if (self._cr & UART.CR_TX_INTEN):
            self.assert_ipl()
        elif (self._cr & UART.CR_RX_INTEN) and len(self._rxfifo) > 0:
            self.assert_ipl()
        else:
            self.deassert_ipl()

    def get_vector(self, interrupt):
        if self._vr > 0:
            return self._vr
        return m68k.IRQ_AUTOVECTOR

    def _handle_console_input(self, input):
        for c in input:
            self._rxfifo.append(c)
        self._update_ipl()


class Timer(Device):
    """
    A simple timebase; reports absolute time in microseconds, and counts down
    microseconds and generates an interrupt.
    """

    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='timer',
                         required_options=['address', 'interrupt'],
                         **options)

        self.add_registers([
            ('COUNT',   0x00, m68k.MEM_SIZE_32, m68k.MEM_READ,  self._read_timebase),
            ('VECTOR',  0x05, m68k.MEM_SIZE_8,  m68k.MEM_READ,  self._read_vector),

            ('COUNT',   0x00, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_countdown),
            ('VECTOR',  0x05, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_vector),
        ])
        self._scaler = int(self.cycle_rate / 1000000)  # 1MHz base clock
        self.reset()

    @classmethod
    def add_arguments(self, parser):
        pass

    def _read_timebase(self):
        return int(self.current_cycle / self._scaler)

    def _read_vector(self):
        return self._r_vector

    def _write_countdown(self, value):
        if value == 0:
            self.deassert_ipl()
            self._deadline = 0
            self.callback_cancel('count')
            self.trace(info='timer cancelled')
        else:
            self._deadline = self.current_cycle + value * self._scaler
            self.callback_at(self._deadline, 'count', self._callback)
            self.trace(info=f'timer set for {self._deadline}, now {self.current_cycle}')

    def _write_vector(self, value):
        self._r_vector = value

    def _callback(self):
        if (self._deadline > 0):
            if (self._deadline <= self.current_cycle):
                self.trace(info='timer expired')
                self.assert_ipl()
                self._deadline = 0
            else:
                self.trace(info='spurious callback')
                self.callback_at(self._deadline, 'count', self._callback)

    def reset(self):
        self._deadline = 0
        self._r_vector = 0
        self.deassert_ipl()
        self.callback_cancel('count')

    def get_vector(self, interrupt):
        self.deassert_ipl()
        if self._r_vector > 0:
            return self._r_vector
        return m68k.IRQ_AUTOVECTOR


class Disk(Device):
    """
    A simple disk device; reads and writes bytes from a file.
    """

    CMD_READ = 0x01
    CMD_WRITE = 0x02

    STATUS_IDLE = 0x00
    STATUS_NOT_READY = 0x01
    STATUS_ERROR = 0x02
    STATUS_DATA_READY = 0x03

    MODE_IDLE = 0
    MODE_READ = 1
    MODE_WRITE = 2

    SECTOR_SIZE = 512

    def __init__(self, args, **options):
        super().__init__(args=args,
                         name='disk',
                         required_options=['address'],
                         **options)
        self.add_registers([
            ('SIZE',    0x04, m68k.MEM_SIZE_32, m68k.MEM_READ,  self._read_size),
            ('STATUS',  0x08, m68k.MEM_SIZE_32, m68k.MEM_READ,  self._read_status),
            ('DATA',    0x0c, m68k.MEM_SIZE_32, m68k.MEM_READ,  self._read_data),

            ('SECTOR',  0x00, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_sector),
            ('COUNT',   0x04, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_count),
            ('COMMAND', 0x08, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_command),
            ('DATA',    0x0c, m68k.MEM_SIZE_32, m68k.MEM_WRITE, self._write_data),
        ])
        self._sector = 0
        self._count = 0
        self._mode = Disk.MODE_IDLE
        self._data_remaining = 0

        if args.diskfile is None:
            self._file_handle = None
            self._disk_size = 0
            self._status = Disk.STATUS_NOT_READY

        else:
            self._file_handle = io.open(args.diskfile, mode='r+b', buffering=0)
            self._file_handle.seek(0, io.SEEK_END)
            filesize = self._file_handle.tell()
            if (filesize % Disk.SECTOR_SIZE) != 0:
                raise RuntimeError(f'disk file {args.diskfile} size {filesize} is not a multiple of {Disk.SECTOR_SIZE}')
            self._disk_size = int(filesize / Disk.SECTOR_SIZE)
            self._status = Disk.STATUS_IDLE

    @classmethod
    def add_arguments(self, parser):
        """add argument definitions for args passed to __init__"""
        parser.add_argument('--diskfile',
                            type=str,
                            default=None,
                            help='disk image file')

    def _read_size(self):
        return self._disk_size

    def _read_status(self):
        return self._status

    def _read_data(self):
        if self._mode == Disk.MODE_READ and self._data_remaining > 0:
            data = self._file_handle.read(4)
            if len(data) != 4:
                raise RuntimeError('unexpected disk file read error')
            value = struct.unpack('>L', data)[0]
            self._data_remaining -= 4
            if self._data_remaining == 0:
                self._status = Disk.STATUS_IDLE
        else:
            self.trace(info='ERROR: read overrun')
            self._status = Disk.STATUS_ERROR
            value = 0

        return value

    def _write_sector(self, value):
        self._sector = value

    def _write_count(self, value):
        self._count = value

    def _write_command(self, value):
        self._mode = Disk.MODE_IDLE
        self._data_remaining = 0

        if value == Disk.CMD_WRITE:
            self.trace(info=f'write {self._sector:#x}/{self._count}')
            self._mode = Disk.MODE_WRITE
        elif value == Disk.CMD_READ:
            self.trace(info=f'read {self._sector:#x}/{self._count}')
            self._mode = Disk.MODE_READ
        else:
            self.trace(info=f'bad cmd {value}')
            self._status = Disk.STATUS_ERROR
            return

        if self._count == 0 or self._count > self._disk_size or (self._disk_size - self._count) < self._sector:
            self.trace(info='ERROR: access beyond end of device')
            self._status = Disk.STATUS_ERROR
            return

        self._file_handle.seek(self._sector * Disk.SECTOR_SIZE)
        self._data_remaining = self._count * Disk.SECTOR_SIZE
        self._status = Disk.STATUS_DATA_READY

    def _write_data(self, value):
        if self._mode == Disk.MODE_WRITE and self._data_remaining > 0:
            data = struct.pack('>L', value)
            self._file_handle.write(data)
            self._data_remaining -= 4
            if self._data_remaining == 0:
                self._status = Disk.STATUS_IDLE
        else:
            self.trace(info='ERROR: write overrun')
            self._status = Disk.STATUS_ERROR
