CC		 = m68k-unknown-elf-gcc
PROG		 = hello
SRCS		 = $(wildcard *.c)
CFLAGS		 = -m68000 \
		   -std=gnu17 \
		   -Wall \
		   -Wextra \
		   -Werror \
		   -Os \
		   -fomit-frame-pointer \
		   -ffreestanding \
		   -nostdlib \
		   -ffunction-sections \
		   -fdata-sections \
		   -Wl,-gc-sections \
		   -Wl,--emit-relocs \
		   -Wl,-z,stack-size=1024 \
		   -Wl,--section-start=.text=0 \
		   -e main

$(PROG): $(SRCS) $(MAKEFILE_LIST)
	$(CC) -o $@ $(CFLAGS) $(SRCS)

.PHONY: clean
clean:
	rm -f $(PROG)