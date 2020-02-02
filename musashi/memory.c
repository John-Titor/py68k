/*
 * Memory model for Musashi 4.x
 */

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

#define MEM_PAGE_SIZE   ((uint32_t)1 << 12)
#define MEM_SIZE        ((uint64_t)1 << 32)
#define MEM_NUM_PAGES   ((uint32_t)(MEM_SIZE / MEM_PAGE_SIZE))
#define MEM_NUM_IDS     64

#define PAGE_ROUND_DOWN(_x) (((uint32_t)(_x)) & (~(MEM_PAGE_SIZE - 1)))
#define PAGE_ROUND_UP(_x) ( (((uint32_t)(_x)) + MEM_PAGE_SIZE - 1)  & (~(MEM_PAGE_SIZE - 1)) ) 

typedef struct
{
    uint8_t     valid:1;
    uint8_t     device:1;
    uint8_t     id:6;
} pte_t;

typedef struct
{
    uint8_t     *buf;
    uint32_t    base;
    uint32_t    size;
    bool        writable;
} mem_buffer_t;

static pte_t                mem_pagetable[MEM_NUM_PAGES];
static mem_buffer_t         mem_buffers[MEM_NUM_IDS];

static bool                 mem_bus_error_enabled;
static bool                 mem_trace_enabled;
static mem_device_handler_t mem_dev_handler;
static mem_trace_handler_t  mem_trace_handler;

__attribute__((unused))
static void
mem_dump_pagetable()
{
    bool dots = false;
    for (uint32_t page = 0; page < MEM_NUM_PAGES; page += 64) {
        bool rowvalid = false;
        for (uint32_t sub = 0; sub < 64; sub++) {
            pte_t pte = mem_pagetable[page + sub];
            if (pte.valid) {
                rowvalid = true;
                break;
            }
        }
        if (!rowvalid) {
            if (!dots) {
                fprintf(stderr, "  ...\n");
                dots = true;
            }
            continue;
        } else {
            dots = false;
        }

        fprintf(stderr, "%08x:", page * MEM_PAGE_SIZE);
        for (uint32_t sub = 0; sub < 64; sub++) {
            if ((sub % 8) == 0) {
                fprintf(stderr, " ");
            }
            pte_t pte = mem_pagetable[page + sub];
            if (pte.valid) {
                if (pte.device) {
                    fprintf(stderr, "*");
                } else {
                    fprintf(stderr, "%c", 'A' + pte.id);
                }
            } else {
                fprintf(stderr, ".");
            }
        }
        fprintf(stderr, "\n");
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

static uint32_t
mem_read(uint32_t address, uint32_t size)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid) {
        if (pte.device) {
            uint32_t ret = mem_dev_handler(MEM_READ, address, size, 0);
//            mem_trace(MEM_READ, address, size, ret);
            return ret;
        } else {
            mem_buffer_t *bp = mem_buffers + pte.id;
            if (bp->buf) {
                uint32_t offset = address - bp->base;
                if ((offset + size) <= bp->size) {
                    uint8_t *dp = bp->buf + offset;
                    uint32_t ret = 0;
                    switch (size) {
                    case MEM_WIDTH_32:
                        ret = *dp++;
                        ret = (ret << 8) + *dp++;
                        // FALLTHROUGH
                    case MEM_WIDTH_16:
                        ret = (ret << 8) + *dp++;
                        // FALLTHROUGH
                    case MEM_WIDTH_8:
                        ret = (ret << 8) + *dp;
                        mem_trace(MEM_READ, address, size, ret);
                        return ret;
                    }
                }
            }

        }
    }
    if (mem_bus_error_enabled) {
        m68k_pulse_bus_error();
    }
    fprintf(stderr, "bad read 0x%x: pte %svalid, %s, id %d\n", 
            address, pte.valid ? "" : "in", pte.device ? "dev" : "mem", pte.id);
    mem_dump_pagetable();
    mem_trace(INVALID_READ, address, size, ~(uint32_t)0);
    return ~(uint32_t)0;
}

static void
mem_write(uint32_t address, uint32_t size, uint32_t value)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid) {
        if (pte.device) {
//            mem_trace(MEM_WRITE, offset, size, value);
            mem_dev_handler(MEM_WRITE, address, size, value);
            return;
        } else {
            mem_buffer_t *bp = mem_buffers + pte.id;
            if (bp->buf && bp->writable) {
                uint32_t offset = address - bp->base;
                if ((offset + size) <= bp->size) {
                    uint8_t *dp = bp->buf + offset;
                    mem_trace(MEM_WRITE, address, size, value);
                    switch (size) {
                    case MEM_WIDTH_32:
                        *dp++ = (value >> 24) & 0xff;
                        *dp++ = (value >> 16) & 0xff;
                        // FALLTHROUGH
                    case MEM_WIDTH_16:
                        *dp++ = (value >> 8) & 0xff;
                        // FALLTHROUGH
                    case MEM_WIDTH_8:
                        *dp = value & 0xff;
                        return;
                    }
                }
            }

        }
    }
    if (mem_bus_error_enabled) {
        m68k_pulse_bus_error();
    }
    mem_trace(INVALID_WRITE, address, size, value);
}

static bool
mem_range_is_free(uint32_t base, uint32_t size)
{
    uint32_t base_page = base / MEM_PAGE_SIZE;
    uint32_t limit_page = (base + size) / MEM_PAGE_SIZE;
    for (uint32_t page_index = base_page; page_index < limit_page; page_index++) {
        if (mem_pagetable[page_index].valid) {
            return false;
        }
    }
    return true;
}

static bool
mem_range_can_be_device(uint32_t base, uint32_t size)
{
    uint32_t base_page = base / MEM_PAGE_SIZE;
    uint32_t limit_page = (base + size) / MEM_PAGE_SIZE;
    for (uint32_t page_index = base_page; page_index < limit_page; page_index++) {
        if (mem_pagetable[page_index].valid && !mem_pagetable[page_index].device) {
            return false;
        }
    }
    return true;
}

static void
mem_set_range(uint32_t base, uint32_t size, pte_t entry)
{
    uint32_t base_page = base / MEM_PAGE_SIZE;
    uint32_t limit_page = (base + size) / MEM_PAGE_SIZE;
    for (uint32_t page_index = base_page; page_index < limit_page; page_index++) {
        mem_pagetable[page_index] = entry;
    }
}

// Emulator API

bool
mem_add_memory(uint32_t base, uint32_t size, bool writable, const void *with_bytes)
{
    // base & size must be aligned
    if ((base % MEM_PAGE_SIZE)
        || (size % MEM_PAGE_SIZE)) {
        return false;
    }

    // get a buffer ID - fail if none available
    uint8_t buffer_id;
    for (buffer_id = 0; ; buffer_id++) {
        if (!mem_buffers[buffer_id].buf) {
            break;
        }
        if (buffer_id >= MEM_NUM_IDS) {
            return false;
        }
    }

    // check that pages aren't already in use
    if (!mem_range_is_free(base, size)) {
        return false;
    }

    // allocate buffer
    mem_buffer_t *bp = mem_buffers + buffer_id;
    bp->buf = calloc(size, 1);
    if (with_bytes) {
        memcpy(bp->buf, with_bytes, size);
    }
    bp->base = base;
    bp->size = size;
    bp->writable = writable;

    // write pagetable
    mem_set_range(base, size, (pte_t){.valid = 1, .device = 0, .id = buffer_id });

    mem_trace(MEM_MAP, base, size, writable ? MEM_MAP_RAM : MEM_MAP_ROM);
    return true;
}

bool
mem_add_device(uint32_t base, uint32_t size)
{
    // must have a device handler
    if (!mem_dev_handler) {
        return false;
    }

    // page-align base & size
    uint32_t aligned_base = PAGE_ROUND_DOWN(base);
    uint32_t aligned_limit = PAGE_ROUND_UP(base + size);
    uint32_t aligned_size = aligned_limit - aligned_base;

    // check that pages are available
    if (!mem_range_can_be_device(aligned_base, aligned_size)) {
        return false;
    }

    // write pagetable
    mem_set_range(aligned_base, aligned_size, (pte_t){.valid = 1, .device = 1, .id = ~0});

    mem_trace(MEM_MAP, aligned_base, aligned_size, MEM_MAP_DEVICE);
    return true;
}

void
mem_set_device_handler(mem_device_handler_t handler)
{
    if (handler) {
        mem_dev_handler = handler;
    }
}

void
mem_set_trace_handler(mem_trace_handler_t handler)
{
    if (handler) {
        mem_trace_handler = handler;
    }
}

void
mem_enable_tracing(bool enable)
{
    mem_trace_enabled = enable && mem_trace_handler;
}

void
mem_enable_bus_error(bool enable)
{
    mem_bus_error_enabled = enable;
}

uint32_t
mem_read_memory(uint32_t address, uint32_t size)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid &&
        !pte.device) {
        mem_buffer_t *bp = mem_buffers + pte.id;
        if (bp->buf) {
            uint32_t offset = address - bp->base;
            if ((offset + size) <= bp->size) {
                uint8_t *dp = bp->buf + offset;
                uint32_t ret = 0;
                switch (size) {
                case MEM_WIDTH_32:
                    ret = *dp++;
                    ret = (ret << 8) + *dp++;
                    // FALLTHROUGH
                case MEM_WIDTH_16:
                    ret = (ret << 8) + *dp++;
                    // FALLTHROUGH
                case MEM_WIDTH_8:
                    ret = (ret << 8) + *dp;
                    return ret;
                }
            }
        }
    }
    return ~(uint32_t)0;
}

void
mem_write_memory(uint32_t address, uint32_t size, uint32_t value)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid
        && !pte.device) {
        mem_buffer_t *bp = mem_buffers + pte.id;
        if (bp->buf) {
            uint32_t offset = address - bp->base;
            if ((offset + size) <= bp->size) {
                uint8_t *dp = bp->buf + offset;
                switch (size) {
                case MEM_WIDTH_32:
                    *dp++ = (value >> 24) & 0xff;
                    *dp++ = (value >> 16) & 0xff;
                    // FALLTHROUGH
                case MEM_WIDTH_16:
                    *dp++ = (value >> 8) & 0xff;
                    // FALLTHROUGH
                case MEM_WIDTH_8:
                    *dp = value & 0xff;
                    return;
                }
            }
        }
    }
    debug("ignored write @ 0x%x, size %d value 0x%x", address, size, value);
}

void
mem_write_bulk(uint32_t address, uint8_t *buffer, uint32_t size)
{
    // could make this faster...
    debug("bulk write 0x%x, from %p size %u", address, buffer, size);
    while (size--) {
        mem_write_memory(address++, MEM_WIDTH_8, *buffer++);
    }
}

// Musashi API

unsigned int
m68k_read_memory_8(unsigned int address)
{
    return mem_read(address, MEM_WIDTH_8);
}

unsigned int
m68k_read_memory_16(unsigned int address)
{
    return mem_read(address, MEM_WIDTH_16);
}

unsigned int
m68k_read_memory_32(unsigned int address)
{
    return mem_read(address, MEM_WIDTH_32);
}

void
m68k_write_memory_8(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_WIDTH_8, value);
}

void
m68k_write_memory_16(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_WIDTH_16, value);
}

void
m68k_write_memory_32(unsigned int address, unsigned int value)
{
    return mem_write(address, MEM_WIDTH_32, value);
}

unsigned int
m68k_read_disassembler_16 (unsigned int address)
{
    return mem_read_memory(address, MEM_WIDTH_16);
}

unsigned int
m68k_read_disassembler_32 (unsigned int address)
{
    return mem_read_memory(address, MEM_WIDTH_32);
}
