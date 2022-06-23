/*
 * Memory model for Musashi 4.x
 */

#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include "m68k.h"
#include "memory.h"

// Internal

#if 0
# define debug(fmt, ...)    fprintf(stderr, "mem: " fmt "\n" , __VA_ARGS__)
#else
# define debug(fmt, ...)    do {} while(0)
#endif

typedef struct
{
    uint8_t     *buf;
    uint32_t    base;
    uint32_t    size;
    bool        writable;
} mem_buffer_t;

#define MEM_MAX_BUFFERS 16
static mem_buffer_t         mem_buffers[MEM_MAX_BUFFERS];
static unsigned             mem_num_buffers = 0;

static bool                 mem_bus_error_enabled;
static bool                 mem_trace_enabled;
static bool                 mem_instr_trace_enabled;
static mem_device_handler_t mem_dev_handler;
static mem_trace_handler_t  mem_trace_handler;
static mem_instr_handler_t  mem_instr_handler;

static uint32_t             mem_fc;
#define FC_IS_PROGRAM       ((mem_fc == 2) || (mem_fc == 6))
#define FC_IS_DATA          ((mem_fc == 1) || (mem_fc == 5))
#define FC_IS_USER          ((mem_fc == 1) || (mem_fc == 2))
#define FC_IS_SUPER         ((mem_fc == 5) || (mem_fc == 6))

void
mem_set_fc(unsigned int new_fc)
{
    mem_fc = new_fc;
}

void
mem_instr_callback(unsigned int pc)
{
    if (mem_instr_trace_enabled && (mem_instr_handler != NULL)) {
        mem_instr_handler(pc);
    }
}

static void
mem_trace(mem_operation_t operation, uint32_t address, uint32_t size, uint32_t value)
{
    if (mem_trace_enabled
        && mem_trace_handler) {
        mem_trace_handler(operation, address, size, value);
    }   
}

static mem_buffer_t *
mem_find(uint32_t address)
{
    // scan buffers for address match
    debug("looking for 0x%x...", address);
    for (unsigned i = 0; i < mem_num_buffers; i++) {
        mem_buffer_t *mb = mem_buffers + i;
        debug("  consider %d:0x%x/0x%x", i, mb->base, mb->size);
        if ((mb->buf != NULL) && 
            (address >= mb->base) &&
            ((address - mb->base) < mb->size)) {
            debug("%s", "  found");
            return mb;
        }
    }
    debug("did not find address 0x%x", address);
    return NULL;
}

static bool
mem_range_is_free(uint32_t base, uint32_t size)
{
    for (unsigned i = 0; i < mem_num_buffers; i++) {
        mem_buffer_t *mb = mem_buffers + i;
        if (mb->buf == NULL) {
            continue;
        }
        if ((base <= mb->base) &&
            ((mb->base - base) < size)) {
            return false;
        }
        if ((mb->base <= base) &&
            ((base - mb->base) < mb->size)) {
            return false;
        }
    }
    return true;
}

static uint32_t
mem_read(uint32_t address, uint32_t size)
{
    mem_buffer_t *mb = mem_find(address);

    if (mb != NULL) {
        uint32_t offset = (address - mb->base);

        // check for overlapping end
        if (offset > (mb->size - (size / 8))) {
            goto bad;
        }

        // do endian swizzle & size conversion        
        uint8_t *mptr = mb->buf + offset;
        uint32_t mem_ret = 0;
        switch (size) {
        case MEM_SIZE_32:
            mem_ret = *mptr++;
            mem_ret = (mem_ret << 8) + *mptr++;
            // FALLTHROUGH
        case MEM_SIZE_16:
            mem_ret = (mem_ret << 8) + *mptr++;
            // FALLTHROUGH
        case MEM_SIZE_8:
            mem_ret = (mem_ret << 8) + *mptr;
            mem_trace(MEM_READ, address, size, mem_ret);
            return mem_ret;
        }
    }

    // try a device operation
    int64_t dev_ret = mem_dev_handler(MEM_READ, address, size, 0);
    if (dev_ret >= 0) {
        return (uint32_t)dev_ret;
    }

bad:
    // nothing handling the op...
    fprintf(stderr, "bad read 0x%x\n", address); 
    mem_trace(INVALID_READ, address, size, ~(uint32_t)0);

    if (mem_bus_error_enabled) {
        m68k_pulse_bus_error();
        m68k_end_timeslice();
    }
    return 0;
}

static void
mem_write(uint32_t address, uint32_t size, uint32_t value)
{
    mem_buffer_t *mb = mem_find(address);

    if (mb != NULL) {
        uint32_t offset = (address - mb->base);

        // check writability
        if (!mb->writable) {
            goto bad;
        }

        // check for overlapping end
        if (offset > (mb->size - (size / 8))) {
            goto bad;
        }

        // do endian swizzle & size conversion        
        uint8_t *mptr = mb->buf + offset;
        mem_trace(MEM_WRITE, address, size, value);
        switch (size) {
        case MEM_SIZE_32:
            *mptr++ = (value >> 24) & 0xff;
            *mptr++ = (value >> 16) & 0xff;
            // FALLTHROUGH
        case MEM_SIZE_16:
            *mptr++ = (value >> 8) & 0xff;
            // FALLTHROUGH
        case MEM_SIZE_8:
            *mptr = value & 0xff;
            return;
        }
    }

    // try a device operation
    int64_t dev_ret = mem_dev_handler(MEM_WRITE, address, size, value);
    if (dev_ret >= 0) {
        return;
    }

bad:
    // nothing handling the op...
    fprintf(stderr, "bad write 0x%x <- 0x%x\n", address, value);
    mem_trace(INVALID_WRITE, address, size, value);

    if (mem_bus_error_enabled) {
        m68k_pulse_bus_error();
        m68k_end_timeslice();
    }
}

// Emulator API

bool
mem_add_memory(uint32_t base, uint32_t size, bool writable)
{
    debug("adding 0x%x/0x%x%s", base, size, writable ? " writable" : "");
    // check for overlap with existing ranges
    if (!mem_range_is_free(base, size)) {
        return false;
    }

    // find a free buffer slot
    mem_buffer_t *mb = NULL;
    for (unsigned i = 0; i < MEM_MAX_BUFFERS; i++) {
        if (mem_buffers[i].buf == NULL) {
            if (i >= mem_num_buffers) {
                mem_num_buffers = i + 1;
            }
            mb = &mem_buffers[i];
            debug("alloc slot %d", i);
            break;
        }
    }
    if (mb == NULL) {
        return false;
    }

    // allocate a new buffer
    mb->buf = calloc(size, 1);
    mb->base = base;
    mb->size = size;
    mb->writable = writable;

    mem_trace(MEM_MAP, base, size, writable ? MEM_MAP_RAM : MEM_MAP_ROM);
    return true;
}

bool
mem_remove_memory(uint32_t base)
{
    // must be referencing the base of a range
    mem_buffer_t *mb = mem_find(base);
    if ((mb == NULL) || (base != mb->base)) {
        return false;
    }

    mem_trace(MEM_UNMAP, mb->base, mb->size, 0);
    free(mb->buf);
    mb->buf = NULL;
    return true;
}

bool
mem_move_memory(uint32_t src, uint32_t dst)
{
    // src must be the base of a range
    mem_buffer_t *mb = mem_find(src);
    if ((mb == NULL) || (src != mb->base)) {
        return false;
    }

    // entire destination must be free
    if (!mem_range_is_free(dst, mb->size)) {
        return false;
    }

    // move it
    mb->base = dst;

    mem_trace(MEM_MOVE, src, mb->size, dst);
    return true;
}

void
mem_set_device_handler(mem_device_handler_t handler)
{
    mem_dev_handler = handler;
}

void
mem_set_trace_handler(mem_trace_handler_t handler)
{
    mem_trace_handler = handler;
}

void
mem_set_instr_handler(mem_instr_handler_t handler)
{
    mem_instr_handler = handler;
}

void
mem_enable_mem_tracing(bool enable)
{
    mem_trace_enabled = enable && mem_trace_handler;
}

void
mem_enable_instr_tracing(bool enable)
{
    mem_instr_trace_enabled = enable && mem_trace_handler;
}

void
mem_enable_bus_error(bool enable)
{
    mem_bus_error_enabled = enable;
}

uint32_t
mem_read_memory(uint32_t address, uint32_t size)
{
    mem_buffer_t *mb = mem_find(address);

    if (mb != NULL) {
        uint32_t offset = (address - mb->base);

        // do endian swizzle & size conversion        
        uint8_t *mptr = mb->buf + offset;
        uint32_t mem_ret = 0;
        switch (size) {
        case MEM_SIZE_32:
            mem_ret = *mptr++;
            mem_ret = (mem_ret << 8) + *mptr++;
            // FALLTHROUGH
        case MEM_SIZE_16:
            mem_ret = (mem_ret << 8) + *mptr++;
            // FALLTHROUGH
        case MEM_SIZE_8:
            mem_ret = (mem_ret << 8) + *mptr;
            mem_trace(MEM_READ, address, size, mem_ret);
            return mem_ret;
        }
    }
    debug("unhandled read at 0x%x/%u", address, size);
    return 0;
}

void
mem_write_memory(uint32_t address, uint32_t size, uint32_t value)
{
    mem_buffer_t *mb = mem_find(address);

    if (mb != NULL) {
        uint32_t offset = (address - mb->base);

        // do endian swizzle & size conversion        
        uint8_t *mptr = mb->buf + offset;
        mem_trace(MEM_WRITE, address, size, value);
        switch (size) {
        case MEM_SIZE_32:
            *mptr++ = (value >> 24) & 0xff;
            *mptr++ = (value >> 16) & 0xff;
            // FALLTHROUGH
        case MEM_SIZE_16:
            *mptr++ = (value >> 8) & 0xff;
            // FALLTHROUGH
        case MEM_SIZE_8:
            *mptr = value & 0xff;
            return;
        }
    }
    debug("ignored write @ 0x%x, size %d value 0x%x", address, size, value);
}

void
mem_write_bulk(uint32_t address, const uint8_t *buffer, uint32_t size)
{
    mem_buffer_t *mb = mem_find(address);
    if (mb != NULL) {
        uint32_t offset = address - mb->base;
        uint32_t space = mb->size - offset;
        uint32_t count = (size <= space) ? size : space;

        debug("loading %d bytes of %d requested to 0x%x", count, size, address);
        memcpy(mb->buf + offset, buffer, count);
    }
}

// Musashi API

unsigned int
m68k_read_memory_8(unsigned int address)
{
    return mem_read(address, MEM_SIZE_8);
}

unsigned int
m68k_read_memory_16(unsigned int address)
{
    return mem_read(address, MEM_SIZE_16);
}

unsigned int
m68k_read_memory_32(unsigned int address)
{
    return mem_read(address, MEM_SIZE_32);
}

unsigned int
m68k_read_immediate_16(unsigned int address)
{
    bool otrace = mem_trace_enabled;
    mem_trace_enabled = false;

    unsigned int result = m68k_read_memory_16(address);
    mem_trace_enabled = otrace;
    return result;
}

unsigned int
m68k_read_immediate_32(unsigned int address)
{
    bool otrace = mem_trace_enabled;
    mem_trace_enabled = false;

    unsigned int result = m68k_read_memory_32(address);
    mem_trace_enabled = otrace;
    return result;
}

unsigned int
m68k_read_pcrelative_8(unsigned int address)
{
    return m68k_read_memory_8(address);
}

unsigned int
m68k_read_pcrelative_16(unsigned int address)
{
    return m68k_read_memory_16(address);
}

unsigned int
m68k_read_pcrelative_32(unsigned int address)
{
    return m68k_read_memory_32(address);
}

void
m68k_write_memory_8(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_SIZE_8, value);
}

void
m68k_write_memory_16(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_SIZE_16, value);
}

void
m68k_write_memory_32(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_SIZE_32, value);
}

unsigned int
m68k_read_disassembler_16 (unsigned int address)
{
    return mem_read_memory(address, MEM_SIZE_16);
}

unsigned int
m68k_read_disassembler_32 (unsigned int address)
{
    return mem_read_memory(address, MEM_SIZE_32);
}
