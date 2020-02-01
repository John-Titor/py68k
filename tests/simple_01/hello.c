/*
 * Simple load-and-go test for the Simple model
 */

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

void
main(void)
{
    puts("Hello Simple!");
    for (;;) ;
}