# Makefile for musashi

OS = $(shell uname -s)
ifeq "$(OS)" "Darwin"
CC = clang
SO_EXT = dylib
else ifeq "$(OS)" "FreeBSD"
CC = clang
SO_EXT = so
else
CC = gcc
SO_EXT = so
endif

#OPT = -g
OPT = -O3 -g

SRC = memory.c callbacks.c m68kcpu.c m68kdasm.c softfloat/softfloat.c
HDR = memory.h m68k.h m68kcpu.h m68kconf.h

GEN_INPUT = m68k_in.c

GEN_SRC = m68kops.c
GEN_HDR = m68kops.h
GEN_FILES = $(GEN_SRC) $(GEN_HDR)

GEN_TOOL_SRC = m68kmake.c
GEN_TOOL = m68kmake

ALL_SRC = $(SRC) $(GEN_SRC)
ALL_HDR = $(HDR) $(GEN_HDR)

LIB = libmusashi.$(SO_EXT)

all: $(LIB)

$(GEN_TOOL): $(GEN_TOOL_SRC)
	$(CC) -O3 -o $@ $(GEN_TOOL_SRC)

$(GEN_FILES): $(GEN_TOOL) $(GEN_INPUT)
	./$(GEN_TOOL)

$(LIB): $(ALL_SRC) $(ALL_HDR)
	$(CC) $(OPT) -fPIC -shared -o $@ $(ALL_SRC)

clean:
	rm -f $(GEN_TOOL) $(GEN_FILES) $(LIB)
