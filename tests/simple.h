/*
 * Register definitions for the Simple emulator model
 */

#include <stdint.h>

#define REG8(_x)            (*(volatile uint8_t *)(_x))
#define REG16(_x)           (*(volatile uint16_t *)(_x))
#define REG32(_x)           (*(volatile uint32_t *)(_x))

#if defined(__mc68010) || defined(__mc68020) || defined(__mc68030) || defined(__mc68040)
# define IO_BASE    0xffff0000
#else
# define IO_BASE    0x00ff0000
#endif

#define UART_BASE   (IO_BASE)
#define TIMER_BASE  (IO_BASE + 0x1000)

#define UART_STATUS     REG8(UART_BASE + 0x01)
#define UART_STATUS_RXRDY   (0x01)
#define UART_STATUS_TXRDY   (0x02)
#define UART_DATA       REG8(UART_BASE + 0x03)
#define UART_CONTROL    REG8(UART_BASE + 0x05)
#define UART_CONTROL_RXIE   (0x01)
#define UART_CONTROL_TXIE   (0x02)
#define UART_VECTOR     REG8(UART_BASE + 0x07)

#define TIMER_PERIOD    REG32(TIMER_BASE + 0x00)
#define TIMER_COUNT     REG32(TIMER_BASE + 0x04)
#define TIMER_CONTROL   REG8(TIMER_BASE + 0x09)
#define TIMER_CONTROL_IE    (0x01)
#define TIMER_VECTOR    REG8(TIMER_BASE + 0x0b)
