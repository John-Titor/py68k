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
#define VEC_AUTOVECTOR(_y)  VECTOR(24 + (_y))   // Autovectored interrupts (1-7)
#define VEC_TRAP(_y)        VECTOR(32 + (_y))   // TRAP instruction vectors (0-15)
#define VEC_USER(_y)        VECTOR(64 + (_y))   // User interrupt vectors (0-63)

/* call this at the head of main() to clear the BSS */
static inline void
early_main()
{
    extern uint32_t __bss_start;
    extern uint32_t _end;
    volatile uint32_t *ptr = &__bss_start;

    while (ptr < &_end) {
        *ptr++ = 0;
    }

    typedef void (*initfunc_t)();
    extern initfunc_t	__init_array_start;
    extern initfunc_t	__init_array_end;
    initfunc_t			*ifp;

    for (ifp = &__init_array_start; ifp < &__init_array_end; ifp++) {
    	(*ifp)();
    }
}

#define set_sr(a)                         		\
    __extension__                             	\
    ({short _r, _a = (a);                     	\
        __asm__ volatile                        \
        ("move.w %%sr,%0\n\t"                   \
         "move.w %1,%%sr"                       \
         : "=&d"(_r)        /* outputs */       \
         : "nd"(_a)         /* inputs  */       \
         : "cc", "memory"   /* clobbered */     \
        );                                      \
        _r;                                     \
    })

static inline void
disable_interrupts()
{
	set_sr(0x2700);
}

static inline void
enable_interrupts()
{
	set_sr(0x2000);
}

extern bool			_detect_native_features(void);
extern uint32_t		_nfID(const char *);
extern uint32_t		_nfCall(uint32_t ID, ...);

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
"        moveq   #0, %d0             /* assume no NatFeats available */ \n"
"        move.l  %sp, %a1                                               \n"
"        move.l  (%a0), %d1                                             \n"
"        move.l  #_fail_nf, (%a0)                                       \n"
"        pea     _nf_version_name                                       \n"
"        sub.l   #4, %sp                                                \n"
"        .dc.w   0x7300              /* NATFEAT_ID */                   \n"
"        tst.l   %d0                                                    \n"
"        jeq     _fail_nf            /* expect non-zero ID */           \n"
"        moveq   #1, %d0             /* NatFeats detected */            \n"
"                                                                       \n"
"_fail_nf:                                                              \n"
"        move.l  %a1, %sp                                               \n"
"        move.l  %d1, (%a0)                                             \n"
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
nf_id(const char *method)
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
        nfid_stderr = nf_id("NF_STDERR");
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
        nfid_shutdown = nf_id("NF_SHUTDOWN");
    }

    if (nfid_shutdown) {
        _nfCall(nfid_shutdown);
    }
    for (;;) ;
}
