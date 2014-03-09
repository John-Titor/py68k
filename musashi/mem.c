/* MusashiCPU <-> vamos memory interface
 *
 * written by Christian Vogelgsang <chris@vogelgsang.org>
 * under the GNU Public License V2
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#include "mem.h"

/* ----- Data ----- */
static uint8_t *ram_data;
static uint     ram_size;
static uint     ram_pages;

static mem_handler_t  mem_handler[MEM_NUM_PAGES];

static invalid_func_t invalid_func;
static int mem_trace = 0;
static trace_func_t trace_func;
static trace_func_t device_func;
static int is_end = 0;

/* ----- Default Funcs ----- */
static void default_invalid(int mode, int width, uint addr)
{
  printf("INVALID: %c(%d): %06x\n",(char)mode,width,addr);
}

static int default_trace(int mode, int width, uint addr, uint val)
{
//  printf("%c(%d): %06x: %x\n",(char)mode,width,addr,val);
  return 0;
}

static int default_device(int mode, int width, uint addr, uint val)
{
  printf("NO DEVICE: %c(%d): %06x: %x\n",(char)mode,width,addr,val);
  return 0;
}

/* ----- End Access ----- */
static uint rx_end(uint addr)
{
  return 0;
}

static uint r16_end(uint addr)
{
  return 0x4e70; // RESET opcode
}

static void wx_end(uint addr, uint val)
{
  // do nothing
}

static mem_handler_t mem_end_handler = {
  rx_end, r16_end, rx_end,
  wx_end, wx_end, wx_end
};

/* ----- Invalid Access ----- */
static void set_all_to_end(void)
{
  int i;
  for(i=0;i<MEM_NUM_PAGES;i++) {
    mem_handler[i] = mem_end_handler;
  }
  is_end = 1;
}

static uint r8_fail(uint addr)
{
  invalid_func('R', 0, addr);
  set_all_to_end();
  return 0;
}

static uint r16_fail(uint addr)
{
  invalid_func('R', 1, addr);
  set_all_to_end();
  return 0;
}

static uint r32_fail(uint addr)
{
  invalid_func('R', 2, addr);
  set_all_to_end();
  return 0;
}

static void w8_fail(uint addr, uint val)
{
  invalid_func('W', 0, addr);
  set_all_to_end();
}

static void w16_fail(uint addr, uint val)
{
  invalid_func('W', 1, addr);
  set_all_to_end();
}

static void w32_fail(uint addr, uint val)
{
  invalid_func('W', 2, addr);
  set_all_to_end();
}

static mem_handler_t mem_fail_handler = {
  r8_fail, r16_fail, r32_fail,
  w8_fail, w16_fail, w32_fail
};

/* ----- RAM access ----- */
static uint r8_ram(uint addr)
{
  return ram_data[addr];
}

static uint r16_ram(uint addr)
{
  return (ram_data[addr] << 8) | ram_data[addr+1];
}

static uint r32_ram(uint addr)
{
  return (ram_data[addr] << 24) | (ram_data[addr+1] << 16) | (ram_data[addr+2] << 8) | (ram_data[addr+3]);
}

static void w8_ram(uint addr, uint val)
{
  ram_data[addr] = val;
}

static void w16_ram(uint addr, uint val)
{
  ram_data[addr] = val >> 8;
  ram_data[addr+1] = val & 0xff;
}

static void w32_ram(uint addr, uint val)
{
  ram_data[addr]   = val >> 24;
  ram_data[addr+1] = (val >> 16) & 0xff;
  ram_data[addr+2] = (val >> 8) & 0xff;
  ram_data[addr+3] = val & 0xff;
}

static mem_handler_t mem_ram_handler = {
  r8_ram, r16_ram, r32_ram,
  w8_ram, w16_ram, w32_ram
};

/* ----- device access ----- */
static uint r8_device(uint addr)
{
  return device_func('R', 0, addr, 0);
}

static uint r16_device(uint addr)
{
  return device_func('R', 1, addr, 0);
}

static uint r32_device(uint addr)
{
  return device_func('R', 2, addr, 0);
}

static void w8_device(uint addr, uint val)
{
  device_func('W', 0, addr, val);
}

static void w16_device(uint addr, uint val)
{
  device_func('W', 1, addr, val);
}

static void w32_device(uint addr, uint val)
{
  device_func('W', 2, addr, val);
}

static mem_handler_t mem_device_handler = {
  r8_device, r16_device, r32_device,
  w8_device, w16_device, w32_device
};

/* ----- Musashi Interface ----- */

unsigned int  m68k_read_memory_8(unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r8(address);
  if(mem_trace) {
    if(trace_func('R',0,address,val)) {
      set_all_to_end();
    }
  }
  return val;
}

unsigned int  m68k_read_pcrelative_8(unsigned int address)
{
  return m68k_read_memory_8(address);
}

unsigned int  m68k_read_memory_16(unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r16(address);
  if(mem_trace) {
    if(trace_func('R',1,address,val)) {
      set_all_to_end();
    }
  }
  return val;
}

unsigned int  m68k_read_immediate_16(unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r16(address);
  if(mem_trace) {
    if(trace_func('I',1,address,val)) {
      set_all_to_end();
    }
  }
  return val;
}

unsigned int  m68k_read_pcrelative_16(unsigned int address)
{
  return m68k_read_memory_16(address);
}

unsigned int  m68k_read_memory_32(unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r32(address);
  if(mem_trace) {
    if(trace_func('R',2,address,val)) {
      set_all_to_end();
    }
  }
  return val;
}

unsigned int  m68k_read_immediate_32(unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r32(address);
  if(mem_trace) {
    if(trace_func('I',2,address,val)) {
      set_all_to_end();
    }
  }
  return val;
}

unsigned int  m68k_read_pcrelative_32(unsigned int address)
{
  return m68k_read_memory_32(address);
}

void m68k_write_memory_8(unsigned int address, unsigned int value)
{
  uint page = MEM_PAGE(address);
  mem_handler[page].w8(address, value);
  if(mem_trace) {
    if(trace_func('W',0,address,value)) {
      set_all_to_end();
    }
  }
}

void m68k_write_memory_16(unsigned int address, unsigned int value)
{
  uint page = MEM_PAGE(address);
  mem_handler[page].w16(address, value);
  if(mem_trace) {
    if(trace_func('W',1,address,value)) {
      set_all_to_end();
    }
  }
}

void m68k_write_memory_32(unsigned int address, unsigned int value)
{
  uint page = MEM_PAGE(address);
  mem_handler[page].w32(address, value);
  if(mem_trace) {
    if(trace_func('W',2,address,value)) {
      set_all_to_end();
    }
  }
}

/* Disassemble support */

unsigned int m68k_read_disassembler_16 (unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r16(address);
  return val;
}

unsigned int m68k_read_disassembler_32 (unsigned int address)
{
  uint page = MEM_PAGE(address);
  uint val = mem_handler[page].r32(address);
  return val;
}

/* ----- API ----- */

int mem_init(uint ram_size_kib)
{
  int i;
  ram_size = ram_size_kib * 1024;
  ram_pages = ram_size_kib / 64;
  ram_data = (uint8_t *)malloc(ram_size);

  for(i=0;i<MEM_NUM_PAGES;i++) {
    if(i < ram_pages) {
      mem_handler[i] = mem_ram_handler;
    } else {
      mem_handler[i] = mem_fail_handler;
    }
  }
  
  trace_func = default_trace;
  invalid_func = default_invalid;
  device_func = default_device;

  return (ram_data != NULL);
}

void mem_free(void)
{
  free(ram_data);
  ram_data = NULL;
}

void mem_set_invalid_func(invalid_func_t func)
{
  invalid_func = func;
}

void mem_set_trace_mode(int on)
{
  mem_trace = on;
}

void mem_set_trace_func(trace_func_t func)
{
  trace_func = func;
}

int mem_is_end(void)
{
  return is_end;
}

void mem_set_device(uint addr)
{
  mem_handler[MEM_PAGE(addr)] = mem_device_handler;
}

void mem_set_device_handler(trace_func_t func)
{
  device_func = func;
}

/* ----- RAM Access ----- */

uint mem_ram_read(int mode, uint addr)
{
  uint val = 0;
  switch(mode) {
    case 0:
      val = r8_ram(addr);
      break;
    case 1:
      val = r16_ram(addr);
      break;
    case 2:
      val = r32_ram(addr);
      break;
  }
  return val;
}

void mem_ram_write(int mode, uint addr, uint value)
{
  switch(mode) {
    case 0:
      w8_ram(addr, value);
      break;
    case 1:
      w16_ram(addr, value);
      break;
    case 2:
      w32_ram(addr, value);
      break;
  }
}

void mem_ram_read_block(uint addr, uint size, char *data)
{
  memcpy(data, ram_data + addr, size);
}

void mem_ram_write_block(uint addr, uint size, const char *data)
{
  memcpy(ram_data + addr, data, size);
}

void mem_ram_clear_block(uint addr, uint size, int value)
{
  memset(ram_data + addr, value, size);
}
