CC		 = m68k-unknown-elf-gcc
SIZE		 = m68k-unknown-elf-size
PROG		 = test

ELF		 = $(PROG).elf
SRCS		 = $(wildcard *.c)
CFLAGS		 = -m68000 \
		   -std=gnu17 \
		   -Wall \
		   -Wextra \
		   -Werror \
		   -Os \
		   -fomit-frame-pointer \
		   -ffreestanding \
		   -nostartfiles \
		   -ffunction-sections \
		   -fdata-sections \
		   -Wl,-gc-sections \
		   -Wl,--emit-relocs \
		   -Wl,-z,stack-size=1048576 \
		   -Wl,--section-start=.text=0 \
		   -MD \
		   -e main

$(ELF): $(SRCS) $(MAKEFILE_LIST)
	$(CC) -o $@ $(CFLAGS) $(SRCS)
	@$(SIZE) $@

.PHONY: clean
clean:
	rm -f $(ELF) *.d

-include *.d
