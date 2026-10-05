#include <stdint.h>

/* ── Symbols from the linker script ─────────────────────────────────────── */
extern uint32_t _data_start;
extern uint32_t _data_end;
extern uint32_t _data_load;
extern uint32_t _bss_start;
extern uint32_t _bss_end;
extern uint32_t _stack_top;   /* top of RAM — used as initial SP */

/* ── Forward declarations ────────────────────────────────────────────────── */
void Reset_Handler(void);
static void Default_Handler(void);

/* Application entry point (defined in main.cpp) */
extern int main(void);

/* Coprocessor Access Control Register (Cortex-M4 System Control Block) */
#define CPACR (*(volatile uint32_t *)0xE000ED88)

/* ── Default handler — weak so any ISR can override it ──────────────────── */
__attribute__((weak)) void NMI_Handler(void)        { Default_Handler(); }
__attribute__((weak)) void HardFault_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void MemManage_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void BusFault_Handler(void)   { Default_Handler(); }
__attribute__((weak)) void UsageFault_Handler(void) { Default_Handler(); }
__attribute__((weak)) void SVC_Handler(void)        { Default_Handler(); }
__attribute__((weak)) void DebugMon_Handler(void)   { Default_Handler(); }
__attribute__((weak)) void PendSV_Handler(void)     { Default_Handler(); }
__attribute__((weak)) void SysTick_Handler(void)    { Default_Handler(); }

/* Device-level IRQ stubs (add real handlers as needed) */
__attribute__((weak)) void IRQ0_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ1_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ2_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ3_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ4_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ5_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ6_Handler(void)  { Default_Handler(); }
__attribute__((weak)) void IRQ7_Handler(void)  { Default_Handler(); }

/* ── Vector table ────────────────────────────────────────────────────────── */
__attribute__((section(".isr_vector")))
void (* const g_pfnVectors[])(void) =
{
    /* Core Cortex-M4 vectors (16 entries) */
    (void (*)(void))((uint32_t)&_stack_top), /* 0: Initial Stack Pointer    */
    Reset_Handler,                           /* 1: Reset                    */
    NMI_Handler,                             /* 2: NMI                      */
    HardFault_Handler,                       /* 3: Hard Fault               */
    MemManage_Handler,                       /* 4: MPU Fault                */
    BusFault_Handler,                        /* 5: Bus Fault                */
    UsageFault_Handler,                      /* 6: Usage Fault              */
    0,                                       /* 7: Reserved                 */
    0,                                       /* 8: Reserved                 */
    0,                                       /* 9: Reserved                 */
    0,                                       /* 10: Reserved                */
    SVC_Handler,                             /* 11: SVCall                  */
    DebugMon_Handler,                        /* 12: Debug Monitor           */
    0,                                       /* 13: Reserved                */
    PendSV_Handler,                          /* 14: PendSV                  */
    SysTick_Handler,                         /* 15: SysTick                 */

    /* Device IRQs (TM4C123GH6PM — first 8 slots; extend as needed) */
    IRQ0_Handler,                            /* 16: GPIO Port A             */
    IRQ1_Handler,                            /* 17: GPIO Port B             */
    IRQ2_Handler,                            /* 18: GPIO Port C             */
    IRQ3_Handler,                            /* 19: GPIO Port D             */
    IRQ4_Handler,                            /* 20: GPIO Port E             */
    IRQ5_Handler,                            /* 21: UART 0                  */
    IRQ6_Handler,                            /* 22: UART 1                  */
    IRQ7_Handler,                            /* 23: SSI 0                   */
};

/* ── Reset handler ───────────────────────────────────────────────────────── */
void Reset_Handler(void)
{
    /* Enable the FPU before anything else runs.
     *
     * This firmware is built -mfpu=fpv4-sp-d16 -mfloat-abi=hard, so the
     * compiler emits VFP instructions inline wherever floats are used. On a
     * Cortex-M4F the FPU is DISABLED out of reset: executing any VFP
     * instruction with CP10/CP11 access denied raises a UsageFault (NOCP),
     * which lands in Default_Handler's infinite loop and the board simply
     * goes quiet. CPACR bits 23:20 grant full access to both coprocessors.
     */
    CPACR |= (0xFu << 20);
    __asm volatile("dsb" ::: "memory");
    __asm volatile("isb" ::: "memory");

    /* Copy initialised data from flash (load address) to RAM (run address) */
    uint32_t *src = &_data_load;
    uint32_t *dst = &_data_start;
    while (dst < &_data_end) {
        *dst++ = *src++;
    }

    /* Zero-initialise .bss */
    dst = &_bss_start;
    while (dst < &_bss_end) {
        *dst++ = 0;
    }

    /* Hand off to the application */
    main();

    /* Should never reach here */
    while (1) {}
}

/* ── Default handler — sits in an infinite loop ──────────────────────────── */
static void Default_Handler(void)
{
    while (1) {}
}
