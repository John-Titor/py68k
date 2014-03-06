/* MusashiCPU <-> vamos memory interface
 *
 * written by Christian Vogelgsang <chris@vogelgsang.org>
 * under the GNU Public License V2
 */

#ifndef _MEM_H
#define _MEM_H

#include "m68k.h"
#include <stdint.h>

/* ------ Defines ----- */

/*
 * Simulate memory decode on 64K boundaries.
 */
#define MEM_MAX_ADDRESS		(1U << 24)
#define MEM_PAGE_SIZE		(1U << 16)
#define MEM_NUM_PAGES		(MEM_MAX_ADDRESS / MEM_PAGE_SIZE)

#define MEM_PAGE(_addr)		(_addr / MEM_PAGE_SIZE)

/* ------ Types ----- */
typedef unsigned int uint;

typedef uint (*read_func_t)(uint addr);
typedef void (*write_func_t)(uint addr, uint value);

typedef void (*invalid_func_t)(int mode, int width, uint addr);
typedef int (*trace_func_t)(int mode, int width, uint addr, uint val);

typedef struct {
  read_func_t	r8;
  read_func_t	r16;
  read_func_t	r32;
  write_func_t	w8;
  write_func_t	w16;
  write_func_t	w32;
} mem_handler_t;

/* ----- API ----- */
extern int  mem_init(uint ram_size_kib);
extern void mem_free(void);

extern void mem_set_invalid_func(invalid_func_t func);
extern int  mem_is_end(void);

extern void mem_set_trace_mode(int on);
extern void mem_set_trace_func(trace_func_t func);

extern void mem_set_device(uint addr);
extern void mem_set_device_handler(trace_func_t func);

extern uint mem_ram_read(int mode, uint addr);
extern void mem_ram_write(int mode, uint addr, uint value);
extern void mem_ram_read_block(uint addr, uint size, char *data);
extern void mem_ram_write_block(uint addr, uint size, const char *data);
extern void mem_ram_clear_block(uint addr, uint size, int value);

#endif
