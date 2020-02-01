/*
 * Linker script for py68k 'simple' device
 */

OUTPUT_ARCH(m68k)
OUTPUT(elf32-m68k)
ENTRY(_reset_vector)

/*
 * 15M of RAM at 0
 */
MEMORY
{
    vectors(rw) : ORIGIN = 0, LENGTH = 1K
    ram(rwx) : ORIGIN = 1K, LENGTH = 15M
}

PROVIDE(_reset_vector = ORIGIN(ram));

SECTIONS
{
    .vectors :
    {
        /* lower m68k vectors */
        _vector_base = .;
        LONG(_stack_top)
        LONG(_reset_vector)
        LONG(vector_bus_error)
        LONG(vector_address_error)
        LONG(vector_illegal_instruction)
        LONG(vector_zero_divide)
        LONG(vector_chk)
        LONG(vector_trapv)
        LONG(vector_privilege_violation)
        LONG(vector_trace)
        LONG(vector_line_a)
        LONG(vector_line_f)
        . = 0x3c;
        LONG(vector_uninitialized_interrupt)
        . = 0x60;
        LONG(vector_spurious_interrupt)

        /* user vectors */
        . = 0x100;
        LONG(vector_64)
        LONG(vector_65)
        LONG(vector_66)
        LONG(vector_67)
        _vector_top = .;

        /* default handlers */
        PROVIDE(vector_bus_error                = vector_unhandled_exception);
        PROVIDE(vector_address_error            = vector_unhandled_exception);
        PROVIDE(vector_illegal_instruction      = vector_unhandled_exception);
        PROVIDE(vector_zero_divide              = vector_unhandled_exception);
        PROVIDE(vector_chk                      = vector_unhandled_exception);
        PROVIDE(vector_trapv                    = vector_unhandled_exception);
        PROVIDE(vector_privilege_violation      = vector_unhandled_exception);
        PROVIDE(vector_trace                    = vector_unhandled_exception);
        PROVIDE(vector_line_a                   = vector_unhandled_exception);
        PROVIDE(vector_line_f                   = vector_unhandled_exception);
        PROVIDE(vector_uninitialized_interrupt  = vector_unhandled_exception);
        PROVIDE(vector_spurious_interrupt       = vector_unhandled_exception);
        PROVIDE(vector_64                       = vector_unhandled_exception);
        PROVIDE(vector_65                       = vector_unhandled_exception);
        PROVIDE(vector_66                       = vector_unhandled_exception);
        PROVIDE(vector_67                       = vector_unhandled_exception);

    } > vectors

    .text:
    {
        _btext = .;
        KEEP(*(.entrypoint))
        *(.text .text.*);
        KEEP(*(INTERRUPT_HANDLERS));
        *(.rodata .rodata.*);
        . = ALIGN(0x4);
        _commands = .;
        KEEP(*(COMMANDS))
        _ecommands = .;
        _etext = .;
        *(.lit);
    } > ram
    
    .data :
    {
        . = ALIGN(0x4);
        *(.got.plt) *(.got);
        *(.shdata);
        *(.data .data.*);
        . = ALIGN(0x4);
        _edata = .;
    } > ram

    .bss :
    {
        . = ALIGN(0x4);
        *(.shbss);
        *(.bss .bss.*);
        *(COMMON);
        _vector_savearea = .;
        . += _vector_top - _vector_base;
        _stack_base = .;
        . = ORIGIN(ram) + LENGTH(ram);
        _stack_top = .;
        _ebss = .;
    } > ram

    .stab 0 (NOLOAD) :
    {
        *(.stab);
    }

    .stabstr 0 (NOLOAD) :
    {
        *(.stabstr);
    }
}

ASSERT((_stack_top - _stack_base) > 2048, "less than 2K stack available")