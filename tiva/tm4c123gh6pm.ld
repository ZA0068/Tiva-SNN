/* Linker script for TM4C123GH6PM
 * Flash: 256 KB at 0x00000000
 * RAM:    32 KB at 0x20000000
 */

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 256K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 32K
}

/* Stack pointer initialised to top of RAM */
_stack_top = ORIGIN(RAM) + LENGTH(RAM);

ENTRY(Reset_Handler)

SECTIONS
{
    /* Interrupt vector table — must be first in flash */
    .isr_vector :
    {
        KEEP(*(.isr_vector))
    } > FLASH

    /* Code and read-only data in flash */
    .text :
    {
        *(.text)
        *(.text.*)
        *(.glue_7)
        *(.glue_7t)
    } > FLASH

    .rodata :
    {
        *(.rodata)
        *(.rodata.*)
    } > FLASH

    /* ARM exception unwinding tables (C++ / libgcc) */
    .ARM.extab :
    {
        *(.ARM.extab*)
    } > FLASH

    .ARM.exidx :
    {
        *(.ARM.exidx*)
    } > FLASH

    /* .data: loaded from flash, runs in RAM */
    _data_load = LOADADDR(.data);

    .data :
    {
        _data_start = .;
        *(.data)
        *(.data.*)
        _data_end = .;
    } > RAM AT > FLASH

    /* .bss: zero-initialised RAM */
    .bss :
    {
        _bss_start = .;
        *(.bss)
        *(.bss.*)
        *(COMMON)
        _bss_end = .;
    } > RAM

    /* Discard C++ exception index when unused */
    /DISCARD/ :
    {
        *(.note.GNU-stack)
    }
}
