import io
import struct
import sys

from device import Device
from musashi import m68k

SECTOR_SIZE = 512

STATUS_ERR = 0x01
STATUS_DRQ = 0x08
STATUS_DF = 0x20
STATUS_DRDY = 0x40
STATUS_BSY = 0x80

ERROR_ABORT = 0x04
ERROR_ID_NOT_FOUND = 0x10
ERROR_UNCORRECTABLE = 0x40

DRH_LBA_EN = 0x40
DRH_HEAD_MASK = 0x0f

CMD_READ_SECTORS = 0x20
CMD_WRITE_SECTORS = 0x30
CMD_IDENTIFY_DEVICE = 0xec

AMODE_READ = 'R'
AMODE_WRITE = 'W'
AMODE_IDENTIFY = 'I'
AMODE_NONE = 'N'


class CompactFlash(Device):
    """
    Memory-mapped CompactFlash emulation.

    Reference: XT13/2008D
    """

    def __init__(self, args, **options):
        super(CompactFlash, self).__init__(args=args,
                                           name='CF',
                                           required_options=['address', 'register_arrangement'],
                                           **options)
        if options['register_arrangement'] == '16-bit':
            self.add_registers([
                ('DATA16',         0x00, m68k.MEM_SIZE_16, m68k.MEM_READ, self._read_data16),
                ('DATA8',          0x01, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_data8),
                ('ERROR',          0x03, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_error),
                ('SECTOR_COUNT',   0x05, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_sector_count),
                ('SECTOR_NUMBER',  0x07, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_sector_number),
                ('CYLINDER_LOW',   0x09, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_cylinder_low),
                ('CYLINDER_HIGH',  0x0b, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_cylinder_high),
                ('DRIVE/HEAD',     0x0d, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_drive_head),
                ('STATUS',         0x0f, m68k.MEM_SIZE_8,  m68k.MEM_READ, self._read_status),

                ('DATA16',         0x00, m68k.MEM_SIZE_16, m68k.MEM_WRITE, self._write_data16),
                ('DATA8',          0x01, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_data8),
                ('FEATURE',        0x03, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_feature),
                ('SECTOR_COUNT',   0x05, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_sector_count),
                ('SECTOR_NUMBER',  0x07, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_sector_number),
                ('CYLINDER_LOW',   0x09, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_cylinder_low),
                ('CYLINDER_HIGH',  0x0b, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_cylinder_high),
                ('DRIVE/HEAD',     0x0d, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_drive_head),
                ('COMMAND',        0x0f, m68k.MEM_SIZE_8,  m68k.MEM_WRITE, self._write_command),
            ])
        elif options['register_arrangement'] == '8-bit':
            self.add_registers([
                ('DATA8',          0x00, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_data8),
                ('ERROR',          0x01, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_error),
                ('SECTOR_COUNT',   0x02, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_sector_count),
                ('SECTOR_NUMBER',  0x03, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_sector_number),
                ('CYLINDER_LOW',   0x04, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cylinder_low),
                ('CYLINDER_HIGH',  0x05, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_cylinder_high),
                ('DRIVE/HEAD',     0x06, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_drive_head),
                ('STATUS',         0x07, m68k.MEM_SIZE_8, m68k.MEM_READ,  self._read_status),

                ('DATA8',          0x00, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_data8),
                ('FEATURE',        0x01, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_feature),
                ('SECTOR_COUNT',   0x02, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_sector_count),
                ('SECTOR_NUMBER',  0x03, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_sector_number),
                ('CYLINDER_LOW',   0x04, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_cylinder_low),
                ('CYLINDER_HIGH',  0x05, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_cylinder_high),
                ('DRIVE/HEAD',     0x06, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_drive_head),
                ('COMMAND',        0x07, m68k.MEM_SIZE_8, m68k.MEM_WRITE, self._write_command),
            ])
        else:
            raise RuntimeError(f'register_arrangement {options["register_arrangement"]} not recognized')

        # open the backing file
        if args.diskfile is not None:
            self._file_handle = io.open(args.diskfile, mode='r+b', buffering=0)
            self._file_handle.seek(0, io.SEEK_END)
            self._file_size = self._file_handle.tell()
            if (self._file_size % SECTOR_SIZE) != 0:
                raise RuntimeError('disk file {} size {} is not a multiple of the sector size'.format(
                    args.diskfile, self._file_size))

            self._r_status = STATUS_DRDY
        else:
            self._file_handle = None
            self._file_size = 0
            self._r_status = STATUS_DF

        drive_size = int(self._file_size / SECTOR_SIZE)
        self._identify_data = struct.pack(
            ''.join(('>',       # little endian
                     'H',       # 0: general config flags
                     'H',       # 1: #cylinders
                     '2x',      # 2: -
                     'H',       # 3: #heads
                     '4x',      # 4-5: -
                     'H',       # 6: #sectors
                     '6x',      # 7-9: -
                     '20s',     # 10-19: serial number
                     '4x',      # 20-21: -
                     'H',       # 22: vendor bytes on READ/WRITE LONG
                     '8s',      # 23-26: firmware version
                     '40s',     # 27-46: model number
                     'H',       # 47: max sectors per READ/WRITE MULTIPLE
                     '2x',      # 48: -
                     'H',       # 49: capabilities
                     '2x',      # 50: -
                     'H',       # 51: PIO timing mode
                     '2x',      # 52: -
                     'H',       # 53: 54-58, 64-70 validity flags
                     '10x',     # 54-58: -
                     'H',       # 59: max sectors / interrupt R/W multiple
                     'H',       # 60: number of addressible sectors (LBA:low)
                     'H',       # 61: number of addressible sectors (LBA:high)
                     '2x',      # 62: -
                     'H',       # 63: DMA modes supported
                     '32x',     # 64-79: -
                     'H',       # 80: ATA major version
                     'H',       # 81: ATA minor version
                     'H',       # 82: command sets supported
                     'H',       # 83: command sets supported
                     '88x',     # 84-127: -
                     'H',       # 128: security status
                     '254x')),  # 129-255: -
            0,                              # 0
            16383,                          # 1
            16,                             # 3
            63,                             # 6
            '00000000'.encode('latin-1'),     # 10-19
            0,                              # 22
            '00000000'.encode('latin-1'),     # 23-26
            'py68k emulated CF   '.encode('latin-1'),  # 27-46
            1,                              # 47
            0,                              # 49
            0,                              # 51
            0,                              # 53
            0,                              # 59
            drive_size & 0xffff,            # 60
            drive_size >> 16,               # 61
            0,                              # 63
            0,                              # 80
            0,                              # 81
            0,                              # 82
            0,                              # 83
            0)                              # 128

        if len(self._identify_data) != SECTOR_SIZE:
            raise RuntimeError(f'IDENTIFY DEVICE data length wrong, {len(self._identify_data)} != 512')

        self._r_error = 0
        self._r_feature = 0
        self._r_sector_count = 0
        self._r_sector_number = 0
        self._r_cylinder = 0
        self._r_drive_head = 0

        self._current_mode = AMODE_NONE
        self._bytes_remaining = 0

    @classmethod
    def add_arguments(cls, parser):
        """add argument definitions for args passed to __init__"""
        parser.add_argument('--diskfile',
                            type=str,
                            default=None,
                            help='CF disk image file')

    def _read_data16(self):
        return self._io_read(m68k.MEM_SIZE_16)

    def _read_data8(self):
        return self._io_read(m68k.MEM_SIZE_8)

    def _read_error(self):
        return self._r_error

    def _read_sector_count(self):
        return self._r_sector_count

    def _read_sector_number(self):
        return self._r_sector_number

    def _read_cylinder_low(self):
        return self._r_cylinder & 0xff

    def _read_cylinder_high(self):
        return self._r_cylinder >> 8

    def _read_drive_head(self):
        return self._r_drive_head

    def _read_status(self):
        return self._r_status

    def _write_data16(self, value):
        self._io_write(m68k.MEM_SIZE_16, value)

    def _write_data8(self, value):
        self._io_write(m68k.MEM_SIZE_8, value)

    def _write_feature(self, value):
        self._r_feature = value

    def _write_sector_count(self, value):
        self._r_sector_count = value

    def _write_sector_number(self, value):
        self._r_sector_number = value

    def _write_cylinder_low(self, value):
        self._r_cylinder = (self._r_cylinder & 0xff00) | value

    def _write_cylinder_high(self, value):
        self._r_cylinder = (self._r_cylinder & 0x00ff) | (value << 8)

    def _write_drive_head(self, value):
        self._r_drive_head = value

    def _write_command(self, value):
        if value == CMD_READ_SECTORS:
            self._trace_io('READ')
            self._do_io(AMODE_READ)

        elif value == CMD_WRITE_SECTORS:
            self._trace_io('WRITE')
            self._do_io(AMODE_WRITE)

        elif value == CMD_IDENTIFY_DEVICE:
            self._trace_io('IDENTIFY')
            self._do_identify()

        else:
            self._r_status = STATUS_ERR
            self._r_error = ERROR_ABORT
            self.trace(info=f'ERROR: command {value:02x} not supported')

    def _trace_io(self, action):
        self.trace(info=f'{action} count {self._r_sector_count} LBA {self._r_lba}')

    def _do_io(self, mode):
        # if we're in the FAULT state (no file, eg.) all I/O fails
        if self._r_status & STATUS_DF:
            self.trace(info=f'ERROR: no device')
            self._r_status |= STATUS_ERR
            self._r_error = ERROR_UNCORRECTABLE
            return

        self._r_status &= ~(STATUS_ERR | STATUS_DRQ)
        self._r_error = 0

        file_byte_offset = self._r_lba * SECTOR_SIZE
        self._bytes_remaining = self._r_sector_count * SECTOR_SIZE
        if self._bytes_remaining == 0:
            self._bytes_remaining = 256 * SECTOR_SIZE

        if (file_byte_offset + self._bytes_remaining) > self._file_size:
            self.trace(info=f'ERROR: access beyond end of device')
            self._r_status |= STATUS_ERR
            self._r_error = ERROR_UNCORRECTABLE

        self._file_handle.seek(file_byte_offset, io.SEEK_SET)
        self._r_status |= STATUS_DRQ
        self._current_mode = mode

    def _do_identify(self):
        self._r_status = STATUS_DRQ
        self._r_error = 0
        self._bytes_remaining = SECTOR_SIZE
        self._current_mode = AMODE_IDENTIFY

    def _io_read(self, width):
        if self._current_mode == AMODE_IDENTIFY:
            pass
        elif self._current_mode == AMODE_READ:
            pass
        else:
            self.trace(info=f'ERROR: data read when not reading / identifying')
            return 0

        if width == m68k.MEM_SIZE_8:
            count = 1
        else:
            count = 2
        if self._bytes_remaining < count:
            self.trace(info=f'ERROR: read beyond sector buffer')
            return 0

        if self._current_mode == AMODE_READ:
            data = self._file_handle.read(count)
            if len(data) != count:
                raise RuntimeError('unexpected disk file read error')

            self._bytes_remaining -= count
            if count == 1:
                return data[0]
            else:
                return (data[1] << 8) + data[0]

        elif self._current_mode == AMODE_IDENTIFY:

            index = SECTOR_SIZE - self._bytes_remaining
            self._bytes_remaining -= count
            if count == 1:
                return self._identify_data[index]
            else:
                return (self._identify_data[index + 1] << 8) + self._identify_data[index]

        else:
            raise RuntimeError('oops')

    def _io_write(self, width, value):
        if self._current_mode != AMODE_WRITE:
            self.trace(info=f'ERROR: data write when not writing')
            return 0

        data = bytearray()
        data.append(value & 0xff)
        if width == m68k.MEM_SIZE_16:
            data.append(value >> 8)

        if self._bytes_remaining < len(data):
            self.trace(info=f'ERROR: write beyond sector buffer')
            return

        self._file_handle.write(data)
        self._bytes_remaining -= len(data)

    @property
    def _r_lba(self):
        if self._r_drive_head & DRH_LBA_EN:
            lba = self._r_sector_number
            lba += self._r_cylinder << 8
            lba += (self._r_drive_head & DRH_HEAD_MASK) << 24
            return lba

        raise RuntimeError('CHS mode not supported')
