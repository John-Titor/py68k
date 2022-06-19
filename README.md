# py68k
M68K emulator based on Musashi, with a Python device model

## running
Launch the console server with `py68k.py --console-server`. This provides vt102 terminal emulation for the console serial port. The console server will stay alive across multiple runs of the emulator.

Launch the emulator itself with `py68k.py --target <target-name> [<target-options>]`. You can pass
`--help` with or without `--target`; if passed with, additional target-specific help may be printed.

## emulations
py68k has a flexible device and target model that makes supporting new targets relatively easy.

See `devices/` for some device examples, and `targets/` for corresponding targets.

### simple
The `simple` target is primarily for emulator testing, though being very simple it's also a good
target for hosting software development. See `devices/simple.py` and `targets/simple.py`.

### Tiny68k
Bill Shen's Tiny68k is a 68000 board with 16M of RAM and a 68681:

https://www.retrobrewcomputers.org/doku.php?id=boards:sbc:tiny68k:tiny68k_rev2

Fetch the Tiny68K monitor / debugger image and CF CP/M image and run:

`./py68k.py --target tiny68k --diskfile t68k_cpm_disk.bin --eeprom T68kbug_r07.BIN`

### P90MB
Bill Shen's P90MB features a Philips P90CE201 68070-based system-on-chip, 512k of flash,
512k of RAM, I2C and three RC2014 slots.

https://www.retrobrewcomputers.org/doku.php?id=builderpages:plasmo:p90mb

Fetch the EPROM file with monitor, CP/M and BASIC, and run:

`./py68k --target p90mb --rom loader1_5+EhBasic+CPM.BIN`

## Requirements

Python, with vt102, pyelftools and hexdump modules installed.
