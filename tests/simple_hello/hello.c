/*
 * Simple load-and-go test for the Simple model
 */

#include <stdbool.h>
#include "../simple.h"

static int
putc(int c)
{
    if (c == '\n') {
        putc('\r');
    }
    while (!(UART_STATUS & UART_STATUS_TXRDY)) {
    }
    UART_DATA = c;
    return c;
}

static void
puts(const char *s)
{
    while (*s) {
        putc(*s++);
    }
    putc('\n');
}

__attribute__((interrupt))
static void
unexpected_exception()
{
    puts("\nEXCEPTION\n");
    for (;;) ;
}

__attribute__((interrupt))
static void
uart_handler()
{
    puts("\nUART\n");
    for (;;) ;
}

__attribute__((interrupt))
static void
timer_handler()
{
    puts("\nTIMER\n");
    for (;;) ;
}


void
main(void)
{
    zero_bss();

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

    puts("Hello Simple!");
    nf_puts("Goodbye Simple!\n");

    UART_CONTROL = UART_CONTROL_TXIE;

    nf_exit();
}