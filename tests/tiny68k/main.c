/*
 * Simple load-and-go test for the Simple model
 */


#include <stdbool.h>
#include <stdio.h>
#include "tiny68k.h"

#undef NDEBUG
#include <assert.h>

__attribute__((interrupt))
static void
unexpected_exception()
{
    fputs("\nUNEXPECTED EXCEPTION\n", stderr);
    nf_exit();
}

volatile int timer_ticks;
__attribute__((interrupt))
static void
duart_handler()
{
    uint8_t status = DUART_ISR;

    if (status & DUART_INT_CTR) {
        (void)DUART_STOPCC;
        timer_ticks++;
    }
}

void
main(void)
{
    early_main();

    /* initialise console UART */
    DUART_MRA = DUART_MR1_8BIT | DUART_MR1_NO_PARITY | DUART_MR1_RTS;
    DUART_MRA = DUART_MR2_CTS_ENABLE_TX | DUART_MR2_1STOP;
    DUART_IVR = 64;
    DUART_ACR = DUART_ACR_MODE_TMR_XTAL16;
    DUART_CTLR = 0x80;
    DUART_CTUR = 0x4;
    DUART_CSRA = DUART_CSR_38400B;
    DUART_CRA = DUART_CR_TXEN | DUART_CR_RXEN;

    // clear any pending interrupt
    (void)DUART_STOPCC;

    // interrupts enabled
    DUART_IMR = DUART_INT_CTR;

    VEC_BUS_ERROR = unexpected_exception;
    VEC_ADDR_ERROR = unexpected_exception;
    VEC_ILLEGAL = unexpected_exception;
    VEC_DIV_ZERO = unexpected_exception;
    VEC_CHK = unexpected_exception;
    VEC_TRAPV = unexpected_exception;
    VEC_PRIV_VIOLATION = unexpected_exception;
    VEC_TRACE = unexpected_exception;
    VEC_LINE_A = unexpected_exception;
    VEC_LINE_F = unexpected_exception;
    VEC_FORMAT_ERROR = unexpected_exception;
    VEC_UNINITIALIZED = unexpected_exception;
    VEC_SPURIOUS = unexpected_exception;
    VEC_AUTOVECTOR(1) = unexpected_exception;
    VEC_AUTOVECTOR(2) = unexpected_exception;
    VEC_AUTOVECTOR(3) = unexpected_exception;
    VEC_AUTOVECTOR(4) = unexpected_exception;
    VEC_AUTOVECTOR(5) = unexpected_exception;
    VEC_AUTOVECTOR(6) = unexpected_exception;
    VEC_AUTOVECTOR(7) = unexpected_exception;
    VEC_USER(0) = duart_handler;

    fprintf(stdout, "stdout test\n");
    fprintf(stderr, "stderr test\n");
    fprintf(stderr, "this is a much longer test of partial writes to stderr\n");

    fprintf(stderr, "vectors at 0x%lx vector 64 at %p is %p duart_handler is %p\n", 
            VECTOR_BASE, &VEC_AUTOVECTOR(6), VEC_USER(0), duart_handler);

    assert(timer_ticks == 0);

    fprintf(stderr, "wait for timer...");
    interrupt_enable(true);
    for (int i = 0; i < 10000; i++) {
        if (timer_ticks > 2) {
            break;
        }
    }
    assert(timer_ticks > 0);
    fprintf(stderr, "timer ticking\n");
    fprintf(stderr, "tests complete\n");
    fflush(stdout);
    nf_exit();
}
