/*
 * Basic m68k support
 */

#include <stdint.h>

#define REG8(_x)            (*(volatile uint8_t *)(_x))
#define REG16(_x)           (*(volatile uint16_t *)(_x))
#define REG32(_x)           (*(volatile uint32_t *)(_x))

#if defined(__mc68010) || defined(__mc68020) || defined(__mc68030) || defined(__mc68040)
static inline uint32_t get_vbr() { uint32_t value; __asm__ volatile ("movec %%vbr, %0" : "=r" (value) : :); return value;}
static inline uint32_t set_vbr() { uint32_t value; __asm__ volatile ("movec %0, %%vbr" : : "r" (value) :); return value;}
# define VECTOR_BASE    get_vbr()
#else
# define VECTOR_BASE    0
#endif

typedef void    (*exception_handler_t)(void);
#define VECTOR(_x)          (*(volatile exception_handler_t *)((_x) * 4 + VECTOR_BASE))

#define VEC_ADDR_ERROR      VECTOR(3)           // Address error
#define VEC_BUS_ERROR       VECTOR(4)           // Illegal instruction
#define VEC_DIV_ZERO        VECTOR(5)           // Zero divide
#define VEC_CHK             VECTOR(6)           // CHK instruction
#define VEC_TRAPV           VECTOR(7)           // TRAPV instruction
#define VEC_PRIV_VIOLATION  VECTOR(8)           // Privilege violation
#define VEC_TRACE           VECTOR(9)           // Trace
#define VEC_LINE_A          VECTOR(10)          // Line 1010 emulator
#define VEC_LINE_F          VECTOR(11)          // Line 1111 emulator
#define VEC_FORMAT_ERROR    VECTOR(14)          // Format error
#define VEC_UNINITIALIZED   VECTOR(15)          // Uninitialized interrupt vector
#define VEC_SPURIOUS        VECTOR(24)          // Spurious interrupt
#define VEC_AUTOVECTOR(_y)  VECTOR(25 + (_y))   // Level 1 on-chip interrupt autovec
#define VEC_TRAP(_y)        VECTOR(32 + (_y))   // TRAP instruction vectors
#define VEC_USER(_y)        VECTOR(64 + (_y))   // User interrupt vectors
