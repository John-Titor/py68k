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

static uint32_t
disk_xfer(uint32_t sector, uint32_t count, uint8_t *buf, bool write)
{
    DISK_SECTOR = sector;
    DISK_COUNT = count;
    DISK_CMD = write ? DISK_CMD_WRITE : DISK_CMD_READ;

    uint32_t status = DISK_STATUS;
    if (status != DISK_STATUS_DATA_READY) {
        return status;
    }
    uint32_t words = count * 512 / 4;
    uint32_t *wbuf = (uint32_t *)buf;
    while (words--) {
        if (write) {
            DISK_DATA = *wbuf++;            
        } else {
            *wbuf++ = DISK_DATA;
        }
    }
    return DISK_STATUS;
}

/*
 * test file starts filled with "1234567\x0a"
 *
 * sector 1: tested for fill pattern
 * sector 3: overwritten with 0x55
 * sector 5,6: overwritten with 0xaa
 */

static bool
disk_read_test()
{
    uint8_t buf[1024];
    bool result = true;

    
    if (disk_xfer(0, 0, buf, false) != DISK_STATUS_ERROR) {
        fprintf(stderr, "read: zero-length test fail\n");
        result = false;
    }
    if (disk_xfer(1000, 1, buf, false) != DISK_STATUS_ERROR) {
        fprintf(stderr, "read: bounds test 1 fail\n");
        result = false;
    }
    if (disk_xfer(7, 2, buf, false) != DISK_STATUS_ERROR) {
        fprintf(stderr, "read: bounds test 2 fail\n");
        result = false;
    }
    if (disk_xfer(0, 1, buf, false) != DISK_STATUS_IDLE) {
        fprintf(stderr, "read: test 1 fail\n");
        result = false;
    }
    if (disk_xfer(7, 1, buf, false) != DISK_STATUS_IDLE) {
        fprintf(stderr, "read: test 2 fail\n");
        result = false;
    }
    if (disk_xfer(1, 2, buf, false) != DISK_STATUS_IDLE) {
        fprintf(stderr, "read: test 3 fail\n");
        result = false;
    }
    if (memcmp(buf, "1234567\x0a", 8)) {
        fprintf(stderr, "read: compare test fail (%.10s)\n", buf);
        result = false;
    }
    return result;
}

static bool
disk_write_test()
{
    uint8_t wbuf[1024];
    uint8_t rbuf[1024];
    bool result = true;

    memset(wbuf, 0x55, sizeof(wbuf));
    if (disk_xfer(3, 1, wbuf, true) != DISK_STATUS_IDLE) {
        fprintf(stderr, "write: test 1 fail\n");
        result = false;
    }
    memset(rbuf, 0, sizeof(rbuf));
    if ((disk_xfer(3, 2, rbuf, false) != DISK_STATUS_IDLE) || memcmp(wbuf, rbuf, 512)) {
        fprintf(stderr, "write: test 1 readback fail/miscompare\n");
        result = false;
    }
    if (memcmp(rbuf + 512, "1234567\x0a", 8)) {
        fprintf(stderr, "write: test 1 overwrite\n");
        result = false;
    }

    memset(wbuf, 0xaa, sizeof(wbuf));
    if (disk_xfer(5, 2, wbuf, true) != DISK_STATUS_IDLE) {
        fprintf(stderr, "write: test 2 fail\n");
        result = false;
    }
    memset(rbuf, 0, sizeof(rbuf));
    if ((disk_xfer(5, 2, rbuf, false) != DISK_STATUS_IDLE) || memcmp(wbuf, rbuf, sizeof(wbuf))) {
        fprintf(stderr, "write: test 2 readback fail/miscompare\n");
        result = false;
    }
    return result;
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
        assert(TIMER_COUNT < (current_time + 50000));
    }
    fprintf(stderr, "countdown interrupt works\n");

    if (DISK_STATUS == DISK_STATUS_NOT_READY) {
        fprintf(stderr, "disk: not ready\n");
    } else if (DISK_SIZE != 8) {
        fprintf(stderr, "disk: wrong size\n");
    } else if (!disk_read_test()) {
        fprintf(stderr, "disk: read test fail\n");
    } else if (!disk_write_test()) {
        fprintf(stderr, "disk: write test fail\n");
    } else {
        fprintf(stderr, "disk: tests pass\n");
    }

    fprintf(stderr, "native features %ssupported\n", _detect_native_features() ? "" : "not ");

    fprintf(stderr, "tests complete\n");
    fflush(stdout);
    nf_exit();
}
