#include <sys/stat.h>
#include <sys/types.h>
#include <sys/fcntl.h>
#include <sys/times.h>
#include <sys/errno.h>
#include <sys/time.h>
#include <stdio.h>

#include "simple.h"
 
void _exit()
{
    nf_exit();
}

int close(int file __unused)
{
    errno = ENOSYS;
    return -1;
}
char **environ = NULL;

int execve(char *name __unused, char **argv __unused, char **env __unused)
{
    errno = ENOSYS;
    return -1;
}

int fork()
{
    errno = ENOSYS;
    return -1;
}

int fstat(int file __unused, struct stat *st __unused)
{
    errno = ENOSYS;
    return -1;
}

int getpid()
{
    errno = ENOSYS;
    return -1;
}

int isatty(int file)
{
    switch (file) {
    case 0:
    case 1:
    case 2:
        return 1;
    default:
        return 0;
    }
}

int kill(int pid __unused, int sig __unused)
{
    errno = ENOSYS;
    return -1;
}

int link(char *old __unused, char *new __unused)
{
    errno = ENOSYS;
    return -1;
}

int lseek(int file __unused, int ptr __unused, int dir __unused)
{
    errno = ENOSYS;
    return -1;
}

int open(const char *name __unused, int flags __unused, ...)
{
    errno = ENOSYS;
    return -1;
}

int read(int file __unused, char *ptr __unused, int len __unused)
{
    /* XXX implement UART input */
    errno = ENOSYS;
    return -1;
}

caddr_t sbrk(int incr)
{
    static caddr_t brk = (caddr_t)&_end;
    caddr_t obrk = brk;

    brk += incr;
    return obrk;
}

int stat(const char *file __unused, struct stat *st __unused)
{
    errno = ENOSYS;
    return -1;
}

clock_t times(struct tms *buf __unused)
{
    return 0;
}

int unlink(char *name __unused)
{
    errno = ENOSYS;
    return -1;
}

int wait(int *status __unused)
{
    errno = ENOSYS;
    return -1;
}

static void
_uputc(char c)
{
    if (c == '\n') {
        _uputc('\r');
    }
    while (!(UART_SR & UART_SR_TXRDY)) {
    }
    UART_DR = c;
}

int write(int file, char *ptr, int len)
{
    int resid = len;
    if (file == 1) {
        while (resid--) {
            _uputc(*ptr++);
        }
    } else if (file == 2) {
        nf_write(ptr, len);
    } else {
        return -1;
    }
    return len;
}

int gettimeofday(struct timeval *__restrict p __unused, void *__restrict tz __unused)
{
    return 0;
}
