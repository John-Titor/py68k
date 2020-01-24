/*
 * Memory model for Musashi 4.x
 */

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "m68k.h"
#include "memory.h"

// Internal

#define MEM_PAGE_SIZE   (1U<<12)
#define MEM_SIZE        (1ULL<<32)
#define MEM_PAGES       (MEM_SIZE / MEM_PAGE_SIZE)
#define MEM_NUM_IDS     64

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

typedef struct
{
    uint32_t    handle;
    uint32_t    base;
    uint32_t    size;
} mem_device_t;

static pte_t                mem_pagetable[MEM_PAGES];
static mem_buffer_t         mem_buffers[MEM_NUM_IDS];
static mem_device_t         mem_devices[MEM_NUM_IDS];

static bool                 mem_bus_error_enabled;
static bool                 mem_trace_enabled;
static mem_device_handler_t mem_dev_handler;
static mem_trace_handler_t  mem_trace_handler;


static void
mem_trace(mem_operation_t operation, uint32_t address, uint8_t width, uint32_t value)
{
    if (mem_trace_enabled
        && mem_trace_handler) {
        mem_trace_handler(operation, address, width, value);
    }   
}

static uint32_t
mem_read(uint32_t address, uint8_t width)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid) {
        if (pte.device) {
            mem_device_t *dp = mem_devices + pte.id;
            if (dp->size) {
                uint32_t offset = address - dp->base;
                uint32_t ret = mem_dev_handler(DEV_READ, dp->handle, offset, width, 0);
                mem_trace(DEV_READ, address, width, ret);
                return ret;
            }
        } else {
            mem_buffer_t *bp = mem_buffers + pte.id;
            if (bp->buf) {
                uint32_t offset = address - bp->base;
                if ((offset + width) <= bp->size) {
                    uint8_t *dp = bp->buf + offset;
                    uint32_t ret = 0;
                    switch (width) {
                    case 4:
                        ret = *dp++;
                        ret = (ret << 8) + *dp++;
                        // FALLTHROUGH
                    case 2:
                        ret = (ret << 8) + *dp++;
                        // FALLTHROUGH
                    case 1:
                        ret = (ret << 8) + *dp;
                        mem_trace(MEM_READ, address, width, ret);
                        return ret;
                    }
                }
            }

        }
    }
    if (mem_bus_error_enabled) {
        m68k_pulse_bus_error();
    }
    mem_trace(INVALID_READ, address, width, ~(uint32_t)0);
    return ~(uint32_t)0;
}

static void
mem_write(uint32_t address, uint8_t width, uint32_t value)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid) {
        if (pte.device) {
            mem_device_t *dp = mem_devices + pte.id;
            if (dp->size) {
                uint32_t offset = address - dp->base;
                mem_trace(DEV_WRITE, offset, width, value);
                mem_dev_handler(DEV_WRITE, dp->handle, offset, width, value);
                return;
            }
        } else {
            mem_buffer_t *bp = mem_buffers + pte.id;
            if (bp->buf && bp->writable) {
                uint32_t offset = address - bp->base;
                if ((offset + width) <= bp->size) {
                    uint8_t *dp = bp->buf + offset;
                    mem_trace(MEM_WRITE, address, width, value);
                    switch (width) {
                    case 4:
                        *dp++ = (value >> 24) & 0xff;
                        *dp++ = (value >> 16) & 0xff;
                        // FALLTHROUGH
                    case 2:
                        *dp++ = (value >> 8) & 0xff;
                        // FALLTHROUGH
                    case 1:
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
    mem_trace(INVALID_WRITE, address, width, value);
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

    return true;
}

bool
mem_add_device(uint32_t base, uint32_t size, uint32_t handle)
{
    // must have a device handler
    if (!mem_dev_handler) {
        return false;
    }

    // base & size must be aligned
    if ((base % MEM_PAGE_SIZE)
        || (size % MEM_PAGE_SIZE)) {
        return false;
    }

    // get a device ID - fail if none available
    uint8_t device_id;
    for (device_id = 0; ; device_id++) {
        if (!mem_buffers[device_id].buf) {
            break;
        }
        if (device_id >= MEM_NUM_IDS) {
            return false;
        }
    }

    // check that pages aren't already in use
    if (!mem_range_is_free(base, size)) {
        return false;
    }

    // allocate device
    mem_device_t *dp = mem_devices + device_id;
    dp->base = base;
    dp->size = size;
    dp->handle = handle;

    // write pagetable
    mem_set_range(base, size, (pte_t){.valid = 1, .device = 1, .id = device_id});

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
mem_read_memory(uint32_t address, uint8_t width)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid &&
        !pte.device) {
        mem_buffer_t *bp = mem_buffers + pte.id;
        if (bp->buf) {
            uint32_t offset = address - bp->base;
            if ((offset + width) <= bp->size) {
                uint8_t *dp = bp->buf + offset;
                uint32_t ret = 0;
                switch (width) {
                case 4:
                    ret = *dp++;
                    ret = (ret << 8) + *dp++;
                    // FALLTHROUGH
                case 2:
                    ret = (ret << 8) + *dp++;
                    // FALLTHROUGH
                case 1:
                    ret = (ret << 8) + *dp;
                    return ret;
                }
            }
        }
    }
    return ~(uint32_t)0;
}

void
mem_write_memory(uint32_t address, uint8_t width, uint32_t value)
{
    pte_t   pte = mem_pagetable[address / MEM_PAGE_SIZE];

    if (pte.valid
        && !pte.device) {
        mem_buffer_t *bp = mem_buffers + pte.id;
        if (bp->buf) {
            uint32_t offset = address - bp->base;
            if ((offset + width) <= bp->size) {
                uint8_t *dp = bp->buf + offset;
                switch (width) {
                case 4:
                    *dp++ = (value >> 24) & 0xff;
                    *dp++ = (value >> 16) & 0xff;
                    // FALLTHROUGH
                case 2:
                    *dp++ = (value >> 8) & 0xff;
                    // FALLTHROUGH
                case 1:
                    *dp = value & 0xff;
                    return;
                }
            }
        }
    }
}

void
mem_write_bulk(uint32_t address, uint8_t *buffer, uint32_t size)
{
    // could make this faster...
    while (size--) {
        mem_write_memory(address++, 1, *buffer++);
    }
}

// Musashi API

unsigned int
m68k_read_memory_8(unsigned int address)
{
    return mem_read(address, 1);
}

unsigned int
m68k_read_memory_16(unsigned int address)
{
    return mem_read(address, 2);
}

unsigned int
m68k_read_memory_32(unsigned int address)
{
    return mem_read(address, 4);
}

void
m68k_write_memory_8(unsigned int address, unsigned int value)
{
    return mem_write(address, 1, value);
}

void
m68k_write_memory_16(unsigned int address, unsigned int value)
{
    return mem_write(address, 2, value);
}

void
m68k_write_memory_32(unsigned int address, unsigned int value)
{
    return mem_write(address, 4, value);
}

unsigned int
m68k_read_disassembler_16 (unsigned int address)
{
    pte_t           pte = mem_pagetable[address / MEM_PAGE_SIZE];
    mem_buffer_t    *bp = mem_buffers + pte.id;
    uint32_t        offset = address - bp->base;

    if (pte.valid
        && !pte.device
        && bp->buf
        && ((offset + 2) <= bp->size)) {

        return (bp->buf[offset] << 8) 
            + bp->buf[offset + 1];
    }
    return 0xffff;
}

unsigned int
m68k_read_disassembler_32 (unsigned int address)
{
    pte_t           pte = mem_pagetable[address / MEM_PAGE_SIZE];
    mem_buffer_t    *bp = mem_buffers + pte.id;
    uint32_t        offset = address - bp->base;

    if (pte.valid
        && !pte.device
        && bp->buf
        && ((offset + 4) <= bp->size)) {

        return (bp->buf[offset] << 8) + bp->buf[offset + 1];
    }
    return 0xffff;
}
