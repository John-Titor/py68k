CC		 = m68k-elf-gcc
SIZE		 = m68k-elf-size
PROG		 = test
DISKFILE	 = disk.dmg

ELF		 = $(PROG).elf
SRCS		 = $(wildcard *.c)
CFLAGS		 = -m68010 \
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
		   -Wl,--section-start=.text=0x1000 \
		   -MD \
		   -e main

$(PROG): $(ELF) $(DISKFILE)

$(ELF): $(SRCS) $(MAKEFILE_LIST)
	$(CC) -o $@ $(CFLAGS) $(SRCS)
	@$(SIZE) $@

.PHONY: $(DISKFILE)
$(DISKFILE):
	yes 1234567 | dd bs=512 count=8 > $@

.PHONY: clean
clean:
	rm -f $(ELF) *.d

-include *.d
