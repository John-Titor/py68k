/*
 * Register definitions for the Simple emulator model
 */

#include "../m68k_misc.h"

#define IO_BASE             0x00ff0000

#define UART_BASE           (IO_BASE)
#define TIMER_BASE          (IO_BASE + 0x1000)

#define UART_SR             REG8(UART_BASE + 0x01)
#define UART_SR_RXRDY           (0x01)
#define UART_SR_TXRDY           (0x02)
#define UART_DR             REG8(UART_BASE + 0x03)
#define UART_CR             REG8(UART_BASE + 0x05)
#define UART_CR_RXINTEN         (0x01)
#define UART_CR_TXINTEN         (0x02)
#define UART_VR             REG8(UART_BASE + 0x07)

#define TIMER_COUNT         REG32(TIMER_BASE + 0x00)
#define TIMER_VECTOR        REG8(TIMER_BASE + 0x05)
