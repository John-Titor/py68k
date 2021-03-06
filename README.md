
# py68k
M68K emulator based on Musashi, with a Python device model

Currently this is being used to model the Tiny68k board by Bill Shen:

https://www.retrobrewcomputers.org/doku.php?id=boards:sbc:tiny68k:tiny68k_rev2

Grab the Tiny68K monitor / debugger image and CF CP/M image and run with something like:

  ./py68k.py --target tiny68k --trace-everything --diskfile t68k_cpm_disk.bin T68kbug_r07.BIN

Exit by hitting ^C three times quickly.

## Requirements

Python, with vt102, pyelftools and hexdump modules installed.

## Todo

 - [ ] memory dump on exit
 - [ ] console transcript
 - [ ] control interface - stop-and-inspect? 
 - [ ] bus / address fault emulation
 - [ ] make it work on Windows with MinGW? Or natively (UniCurses, DLL evil)?
