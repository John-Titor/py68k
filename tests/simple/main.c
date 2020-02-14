/*
 * Simple load-and-go test for the Simple model
 */


#include <stdbool.h>
#include <stdio.h>
#include "simple.h"

#undef NDEBUG
#include <assert.h>

__attribute__((interrupt))
static void
unexpected_exception()
{
    fputs("\nEXCEPTION\n", stderr);
    for (;;) ;
}

__attribute__((interrupt))
static void
uart_handler()
{
    fputs("\nUART\n", stderr);
    UART_CR = 0;
}

volatile int timer_ticks;
__attribute__((interrupt))
static void
timer_handler()
{
    fprintf(stderr, "timer interrupt at %lu\n", TIMER_COUNT);
    timer_ticks++;
}

void
main(void)
{
    early_main();

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
    VEC_AUTOVECTOR(2) = uart_handler;
    VEC_AUTOVECTOR(3) = unexpected_exception;
    VEC_AUTOVECTOR(4) = unexpected_exception;
    VEC_AUTOVECTOR(5) = unexpected_exception;
    VEC_AUTOVECTOR(6) = timer_handler;
    VEC_AUTOVECTOR(7) = unexpected_exception;

    fprintf(stdout, "stdout test\n");
    fprintf(stderr, "stderr test\n");
    fprintf(stderr, "this is a much longer test of partial writes to stderr\n");

    fprintf(stderr, "vectors at 0x%lx autovector 6 at %p is %p timer_handler is %p\n", 
            VECTOR_BASE, &VEC_AUTOVECTOR(6), VEC_AUTOVECTOR(6), timer_handler);

    assert(TIMER_COUNT != 0);

    interrupt_enable(true);
    uint32_t current_time = TIMER_COUNT;
    fprintf(stderr, "current_time %lu\n", current_time);
    for (int i = 0; i < 10000; i++) {
        if (TIMER_COUNT != current_time) {
            break;
        }
    }
    assert (TIMER_COUNT != current_time);
    fprintf(stderr, "time advances\n");
    current_time = TIMER_COUNT;
    TIMER_COUNT = 500;
    while (timer_ticks == 0) {
        assert(TIMER_COUNT < (current_time + 5000));
    }
    fprintf(stderr, "countdown interrupt works\n");
    fprintf(stderr, "tests complete\n");
    fflush(stdout);
    nf_exit();
}
