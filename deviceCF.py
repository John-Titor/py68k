import sys
import io
from device import device


class CompactFlash(device):
    """
    CompactFlash emulation

    Reference: XT13/2008D
    """

    SECTOR_SIZE = 512

    REG_DATA16 = 0x00
    REG_DATA8 = 0x01
    REG_ERROR = 0x03
    REG_FEATURE = 0x03
    REG_SECTOR_COUNT = 0x05
    REG_SECTOR_NUMBER = 0x07
    REG_CYLINDER_LOW = 0x09
    REG_CYLINDER_HIGH = 0x0b
    REG_DRIVE_HEAD = 0x0d
    REG_STATUS = 0x0f
    REG_COMMAND = 0x0f

    _registers = {
        'DATA16' : 0x00,
        'DATA8' : 0x01,
        'ERROR/FEATURE': 0x03,
        'SECTOR_COUNT' : 0x05,
        'SECTOR_NUMBER': 0x07,
        'CYLINDER_LOW' : 0x09,
        'CYLINDER_HIGH': 0x0b,
        'DRIVE/HEAD' : 0x0d,
        'STATUS/COMMAND': 0x0f
    }

    STATUS_ERR = 0x01
    STATUS_DRQ = 0x08
    STATUS_DF = 0x20
    STATUS_DRDY = 0x40
    STATUS_BSY = 0x80

    ERROR_ID_NOT_FOUND = 0x10
    ERROR_UNCORRECTABLE = 0x40

    DRH_LBA_EN = 0x40
    DRH_HEAD_MASK = 0x0f

    CMD_READ_SECTORS = 0x20
    CMD_WRITE_SECTORS = 0x30

    AMODE_READ = 'R'
    AMODE_WRITE = 'W'
    AMODE_NONE = 'N'

    def __init__(self, args, address, interrupt, debug):
        super(CompactFlash, self).__init__('CF', address=address, debug=debug)
        self.map_registers(CompactFlash._registers)

        # open the backing file
        if args.diskfile is not None:
            self._file_handle = io.open(args.diskfile, mode='r+b', buffering=0)
            self._file_handle.seek(0, io.SEEK_END)
            self._file_size = self._file_handle.tell()
            if (self._file_size % CompactFlash.SECTOR_SIZE) != 0:
                raise RuntimeError('disk file {} size {} is not a multiple of the sector size'.format(
                    args.diskfile, self._file_size))

            self._r_status = CompactFlash.STATUS_DRDY
        else:
            self._file_handle = None
            self._file_size = 0
            self._r_status = CompactFlash.STATUS_DF

        self._r_error = 0
        self._r_feature = 0
        self._r_sector_count = 0
        self._r_sector_number = 0
        self._r_cylinder = 0
        self._r_drive_head = 0

        self._current_mode = CompactFlash.AMODE_NONE
        self._bytes_remaining = 0

    def read(self, width, offset):
        if offset == CompactFlash.REG_DATA16:
            value = self._io_read(width)

        elif offset == CompactFlash.REG_DATA8:
            value = self._io_read(width)

        elif offset == CompactFlash.REG_ERROR:
            value = self._r_error

        elif offset == CompactFlash.REG_SECTOR_COUNT:
            value = self._r_sector_count

        elif offset == CompactFlash.REG_SECTOR_NUMBER:
            value = self._r_sector_number

        elif offset == CompactFlash.REG_CYLINDER_LOW:
            value = self._r_cylinder & 0xff

        elif offset == CompactFlash.REG_CYLINDER_HIGH:
            value = self._r_cylinder >> 8

        elif offset == CompactFlash.REG_DRIVE_HEAD:
            value = self._r_drive_head

        elif offset == CompactFlash.REG_STATUS:
            value = self._r_status

        else:
            raise RuntimeError('read from 0x{:02x} not handled'.format(offset))

        return value

    def write(self, width, offset, value):
        if offset == CompactFlash.REG_DATA16:
            self._io_write(width, value)

        elif offset == CompactFlash.REG_DATA8:
            self._io_write(width, value)

        elif offset == CompactFlash.REG_FEATURE:
            self._r_feature = value

        elif offset == CompactFlash.REG_SECTOR_COUNT:
            self._r_sector_count = value

        elif offset == CompactFlash.REG_SECTOR_NUMBER:
            self._r_sector_number = value

        elif offset == CompactFlash.REG_CYLINDER_LOW:
            self._r_cylinder = (self._r_cylinder & 0xff00) | value

        elif offset == CompactFlash.REG_CYLINDER_HIGH:
            self._r_cylinder = (self._r_cylinder & 0x00ff) | (value << 8)

        elif offset == CompactFlash.REG_DRIVE_HEAD:
            self._r_drive_head = value

        elif offset == CompactFlash.REG_COMMAND:
            self._command(value)

        else:
            raise RuntimeError('write to 0x{:02x} not handled'.format(offset))

    def _command(self, command):
        if command == CompactFlash.CMD_READ_SECTORS:
            self._trace_io('READ')
            self._do_io(CompactFlash.AMODE_READ)

        elif command == CompactFlash.CMD_WRITE_SECTORS:
            self._trace_io('WRITE')
            self._do_io(CompactFlash.AMODE_WRITE)
        else:
            raise RuntimeError(
                'CF command {:02x} not supported'.format(command))

    def _trace_io(self, action):
        self.trace(action, 'count {} LBA {}'.format(
            self._r_sector_count, self._r_lba))

    def _do_io(self, mode):
        # if we're in the FAULT state (no file, eg.) all I/O fails
        if self._r_status & CompactFlash.STATUS_DF:
            self.trace('IOERR', 'no device')
            self._r_status |= CompactFlash.STATUS_ERR
            self._r_error = CompactFlash.ERROR_UNCORRECTABLE
            return

        self._r_status &= ~(CompactFlash.STATUS_ERR | CompactFlash.STATUS_DRQ)
        self._r_error = 0

        file_byte_offset = self._r_lba * CompactFlash.SECTOR_SIZE
        self._bytes_remaining = self._r_sector_count * CompactFlash.SECTOR_SIZE
        if self._bytes_remaining == 0:
            self._bytes_remaining = 256 * CompactFlash.SECTOR_SIZE

        if (file_byte_offset + self._bytes_remaining) > self._file_size:
            self.trace('IOERR', 'access beyond end of device')
            self._r_status |= CompactFlash.STATUS_ERR
            self._r_error = CompactFlash.ERROR_UNCORRECTABLE

        self._file_handle.seek(file_byte_offset, io.SEEK_SET)
        self._r_status |= CompactFlash.STATUS_DRQ
        self._current_mode = mode

    def _io_read(self, width):
        if self._current_mode != CompactFlash.AMODE_READ:
            self.trace('IOERR', 'data read when not reading')
            return 0

        if width == device.WIDTH_8:
            count = 1
        else:
            count = 2

        if self._bytes_remaining < count:
            self.trace('IOERR', 'read beyond sector buffer')
            return 0

        data = self._file_handle.read(count)
        if len(data) != count:
            raise RuntimeError('unexpected disk file read error')

        self._bytes_remaining -= count
        if width == device.WIDTH_8:
            return ord(data[0])
        else:
            return (ord(data[1]) << 8) + ord(data[0])

    def _io_write(self, width, value):
        if self._current_mode != CompactFlash.AMODE_WRITE:
            self.trace('IOERR', 'data write when not writing')
            return 0

        if width == device.WIDTH_8:
            data = [value]
        else:
            data = [value & 0xff, value >> 8]

        if self._bytes_remaining < len(data):
            self.trace('IOERR', 'write beyond sector buffer')
            return

        self._file_handle.write(data)
        self._bytes_remaining -= len(data)

    @property
    def _r_lba(self):
        if self._r_drive_head & CompactFlash.DRH_LBA_EN:
            lba = self._r_sector_number
            lba += self._r_cylinder << 8
            lba += (self._r_drive_head & CompactFlash.DRH_HEAD_MASK) << 24
            return lba

        raise RuntimeError('CHS mode not supported')
