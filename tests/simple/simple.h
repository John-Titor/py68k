/*
 * Register definitions for the Simple emulator model
 */

#include "../m68k_misc.h"

#define IO_BASE             0x00ff0000

#define UART_BASE           (IO_BASE)
#define TIMER_BASE          (IO_BASE + 0x1000)
#define DISK_BASE           (IO_BASE + 0x2000)

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

#define DISK_SECTOR         REG32(DISK_BASE + 0x00)
#define DISK_SIZE           REG32(DISK_BASE + 0x04)
#define DISK_COUNT          REG32(DISK_BASE + 0x04)
#define DISK_STATUS         REG32(DISK_BASE + 0x08)
#define DISK_STATUS_IDLE        (0x00)
#define DISK_STATUS_NOT_READY   (0x01)
#define DISK_STATUS_ERROR       (0x02)
#define DISK_STATUS_DATA_READY  (0x03)
#define DISK_CMD            REG32(DISK_BASE + 0x08)
#define DISK_CMD_READ           (0x01)
#define DISK_CMD_WRITE          (0x02)
#define DISK_DATA           REG32(DISK_BASE + 0x0c)
