# Makefile for TM4C123GH6PM bare-metal C++ project
# Toolchain: arm-none-eabi-gcc (GCC ARM Embedded)
#
# Targets:
#   all   — build $(TARGET).elf and $(TARGET).bin
#   flash — program via lm4flash (install: https://github.com/utzig/lm4tools)
#           NOTE: if multiple Tiva devices are connected, pass the USB device
#           explicitly: make flash LMDEV=/dev/ttyACM0
#   clean — remove build artefacts

# ── Toolchain ────────────────────────────────────────────────────────────────
PREFIX   := arm-none-eabi-
CC       := $(PREFIX)gcc
CXX      := $(PREFIX)g++
LD       := $(PREFIX)g++
OBJCOPY  := $(PREFIX)objcopy

# ── Target ───────────────────────────────────────────────────────────────────
TARGET   := hello_tiva

# ── Sources & objects ────────────────────────────────────────────────────────
SRCS     := startup.c main.cpp
OBJS     := $(patsubst %.c,%.o,$(patsubst %.cpp,%.o,$(SRCS)))

# ── CPU / FPU flags ───────────────────────────────────────────────────────────
CPU_FLAGS := -mcpu=cortex-m4 \
             -mthumb         \
             -mfpu=fpv4-sp-d16 \
             -mfloat-abi=hard

# ── Compiler flags ────────────────────────────────────────────────────────────
# -O0, not -O2: the combined firmware (UART + SysTick + sensor acquisition)
# hangs/faults silently under -O2 on this toolchain (arm-none-eabi-gcc,
# lm4tools stack) — confirmed by bisecting the exact same source at -O0 vs
# -O2, where -O0 runs correctly and -O2 produces no output at all. Root
# cause not fully isolated; -O0 is the verified-working choice for now.
# Code size is a non-issue here (a few KB against a 256K budget).
# -MMD -MP emits a .d file per object listing the headers it included, so
# regenerating sltc_weights.h actually forces a rebuild. Without this, the
# pattern rules below depend only on the .cpp: retraining and running
# `make flash` would silently reflash the PREVIOUS weights, because main.o
# still looked up to date.
DEPFLAGS := -MMD -MP

CFLAGS   := -std=c11   -O0 -Wall -ffunction-sections -fdata-sections $(DEPFLAGS) $(CPU_FLAGS)
CXXFLAGS := -std=c++17 -O0 -Wall -ffunction-sections -fdata-sections $(DEPFLAGS) $(CPU_FLAGS)

# ── Linker flags ──────────────────────────────────────────────────────────────
LDFLAGS  := -T tm4c123gh6pm.ld \
            -Wl,--gc-sections  \
            -nostartfiles      \
            $(CPU_FLAGS)

# ── lm4flash options (override LMDEV on the command line if needed) ────────────
LMDEV    :=
FLASHCMD := lm4flash $(if $(LMDEV),--device $(LMDEV),) $(TARGET).bin

# ── Rules ─────────────────────────────────────────────────────────────────────
.PHONY: all flash clean

all: $(TARGET).elf $(TARGET).bin

# Link
$(TARGET).elf: $(OBJS)
	$(LD) $(LDFLAGS) -o $@ $^

# Binary image
$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@

# C sources
%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

# C++ sources
%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c -o $@ $<

# Flash to board
flash: $(TARGET).bin
	$(FLASHCMD)

clean:
	rm -f $(OBJS) $(OBJS:.o=.d) $(TARGET).elf $(TARGET).bin

# Header dependencies discovered by -MMD. The dash suppresses the "no such
# file" noise on a clean tree, where the .d files don't exist yet.
-include $(OBJS:.o=.d)
