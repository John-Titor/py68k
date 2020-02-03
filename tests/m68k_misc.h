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
#define VECTOR(_x)          (*((volatile exception_handler_t *)((_x) * 4 + VECTOR_BASE)))

#define VEC_BUS_ERROR       VECTOR(2)           // Bus error
#define VEC_ADDR_ERROR      VECTOR(3)           // Address error
#define VEC_ILLEGAL         VECTOR(4)           // Illegal instruction
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

static inline void
zero_bss()
{
    extern uint32_t __bss_start;
    extern uint32_t _end;
    uint32_t *ptr = &__bss_start;

    while (ptr < &_end) {
        *ptr++ = 0;
    }
}

extern bool _detect_native_features(void);
extern uintptr_t _nfID(const char *);
extern uint32_t _nfCall(uint32_t ID, ...);

/*
 * d0 - return code
 * d1 - old illegal vector
 * a0 - address of illegal vector
 * a1 - old sp
 */
__asm__
(
#if defined(__mc68010) || defined(__mc68020) || defined(__mc68030) || defined(__mc68040)
"        movec   %vbr, %a0                                              \n"
"        add.l   #0x10, %a0                                             \n"
#else
"        move.l  #0x10, %a0                                             \n"
#endif
"_detect_native_features:                                               \n"
"        moveq   #0,%d0              /* assume no NatFeats available */ \n"
"        move.l  %sp,%a1                                                \n"
"        move.l  (%a0),%d1                                              \n"
"        move.l  #_fail_natfeat, (%a0)                                  \n"
"        pea     _nf_version_name                                       \n"
"        sub.l   #4,%sp                                                 \n"
"        .dc.w   0x7300              /* Jump to NATFEAT_ID */           \n"
"        tst.l   %d0                                                    \n"
"        jeq     _fail_natfeat                                          \n"
"        moveq   #1,%d0              /* NatFeats detected */            \n"
"                                                                       \n"
"_fail_natfeat:                                                         \n"
"        move.l  %a1,%sp                                                \n"
"        move.l  %d1,(%a0)                                              \n"
"                                                                       \n"
"        rts                                                            \n"
"                                                                       \n"
"_nf_version_name:                                                      \n"
"        .ascii  \"NF_VERSION\\0\"                                      \n"
"        .even                                                          \n"
"                                                                       \n"
"_nfID:                                                                 \n"
"        .dc.w   0x7300                                                 \n"
"        rts                                                            \n"
"_nfCall:                                                               \n"
"        .dc.w   0x7301                                                 \n"
"        rts                                                            \n"
);

static uint32_t
nfID(const char *method)
{
    static bool probed, supported;

    if (!probed && _detect_native_features()) {
        supported = true;
    }
    probed = true;
    if (supported) {
        return _nfID(method);
    }
    return 0;
}

static void
nf_puts(const char *str)
{
    static uint32_t nfid_stderr = 0;

    if (!nfid_stderr) {
        nfid_stderr = nfID("NF_STDERR");
    }

    if (nfid_stderr) {
        _nfCall(nfid_stderr, str);
    }
}

static void
nf_exit()
{
    static uint32_t nfid_shutdown = 0;

    if (!nfid_shutdown) {
        nfid_shutdown = nfID("NF_SHUTDOWN");
    }

    if (nfid_shutdown) {
        _nfCall(nfid_shutdown);
    }
    for (;;) ;
}
