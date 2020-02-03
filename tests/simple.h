/*
 * Register definitions for the Simple emulator model
 */

#include "m68k_misc.h"

#define IO_BASE             0x00ff0000

#define UART_BASE           (IO_BASE)
#define TIMER_BASE          (IO_BASE + 0x1000)

#define UART_STATUS         REG8(UART_BASE + 0x01)
#define UART_STATUS_RXRDY       (0x01)
#define UART_STATUS_TXRDY       (0x02)
#define UART_DATA           REG8(UART_BASE + 0x03)
#define UART_CONTROL        REG8(UART_BASE + 0x05)
#define UART_CONTROL_RXIE       (0x01)
#define UART_CONTROL_TXIE       (0x02)
#define UART_VECTOR         REG8(UART_BASE + 0x07)

#define TIMER_PERIOD        REG32(TIMER_BASE + 0x00)
#define TIMER_COUNT         REG32(TIMER_BASE + 0x04)
#define TIMER_CONTROL       REG8(TIMER_BASE + 0x09)
#define TIMER_CONTROL_IE        (0x01)
#define TIMER_VECTOR        REG8(TIMER_BASE + 0x0b)
