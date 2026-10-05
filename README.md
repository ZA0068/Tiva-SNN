# Tiva SNN

A tiny **spiking liquid-time-constant (sLTC) network** running bare-metal on a **TM4C123G LaunchPad (Tiva C-Series)**. It classifies live accelerometer motion as *smooth* or *turbulent* in real time. The repo also holds the Podman dev environment (ARM toolchain, `lm4flash`, ROS2 Humble) and the host-side recording and training pipeline.

```
 BOOSTXL-EDUMKII          TM4C123G (bare metal, 100 Hz)                     Host
┌──────────────┐  ADC0  ┌──────────────────────────────────────┐  UART0  ┌──────────────────────┐
│ analog accel │──────▶│ counts→g ─▶ InputEncoder ─▶ sLTC (4) │──ICDI──▶│ record_dataset.py    │
│ X/Y/Z (PD0-2)│        │                    ─▶ readout ─▶ LED │  USB    │ train_sltc.py        │
└──────────────┘        └──────────────────────────────────────┘         │  └▶ sltc_weights.h ──┼─▶ reflash
                                                                         └──────────────────────┘
```

---

## 1. Overview

| Layer | Toolchain / tech |
|---|---|
| MCU firmware | `gcc-arm-none-eabi`, C++17, pure register access (no TivaWare) |
| Sensor | BOOSTXL-EDUMKII analog 3-axis accelerometer via ADC0 |
| On-device model | 4-neuron recurrent sLTC + 2-class linear readout (`tiva/sltcneuron.hpp`) |
| Flashing | `lm4flash` (built from source in the image) |
| Serial capture | `pyusb` speaking CDC-ACM directly over usbfs (`scripts/tiva_serial.py`) |
| Training | PyTorch, BPTT with surrogate gradients (`training/train_sltc.py`, runs on the host) |
| Host middleware | ROS2 Humble (`ros-humble-ros-base`), placeholder node only so far |
| Container runtime | Podman + podman-compose |

**Hardware:**
- EK-TM4C123GXL LaunchPad (TM4C123GH6PM, Cortex-M4F, running from the 16 MHz PIOSC)
- BOOSTXL-EDUMKII (Educational BoosterPack MK II), stacked directly on the LaunchPad headers

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| **Podman** ≥ 4.x | `sudo apt install podman` / `sudo pacman -S podman` |
| **podman-compose** | `pip install podman-compose` (`docker compose` also works with `compose.yaml`) |
| **udev rules / plugdev** | Needed for USB access to the ICDI (`1cbe:00fd`). See [utzig/lm4tools](https://github.com/utzig/lm4tools) for the rule. |
| **Python 3 + PyTorch** (host) | For `training/train_sltc.py` |
| **pyusb** | For `scripts/tiva_serial.py` and its callers: `pip install pyusb` (not yet in the Containerfile) |

> **udev tip:** Copy the lm4tools udev rule to `/etc/udev/rules.d/`, then run `sudo udevadm control --reload-rules && sudo udevadm trigger`. Add your user to `plugdev` if needed.

---

## 3. Quick Start

> **Space-in-path workaround:** The overlay filesystem driver can't handle spaces in mount paths, so `podman-compose up --build` fails while the project lives in `Tiva SNN`. `scripts/build_image.sh` builds through a `/tmp/tiva-snn-build` symlink instead. After that, plain `podman-compose up` works.

```bash
# 1. Build the image
bash scripts/build_image.sh

# 2. Start the container (detached)
podman-compose up -d

# 3. Open a shell inside it
podman-compose exec tiva-snn-dev bash

# 4. Inside the container: build and flash the firmware
bash scripts/build_tiva.sh
bash scripts/flash_tiva.sh
```

On start, the container runs `scripts/setup_usb_symlink.sh`. That script finds the LaunchPad by VID:PID in sysfs and links `/dev/Tiva/LaunchPad` to its current `/dev/bus/usb/BBB/DDD` node, which changes on every replug. Every bash session sources ROS2 Humble and the workspace overlay through `/etc/bash.bashrc`.

---

## 4. Firmware (`tiva/`)

### What it does

`tiva/main.cpp` is an analog accelerometer logger with on-device classification:

1. **Samples** X/Y/Z on ADC0 sequencer 0 (AIN7/AIN6/AIN5 on PD0/PD1/PD2) with 64× hardware oversampling.
2. **Converts** counts to g using a measured calibration (`ACCEL_ZERO_G_COUNTS = 2048`, `ACCEL_COUNTS_PER_G = 828`).
3. **Encodes** the sample with `InputEncoder` and steps the **sLTC network** once.
4. **Streams** one CSV line per sample over UART0 at 115200 8N1:
   ```
   time_ms,accel_x_g,accel_y_g,accel_z_g,raw_x,raw_y,raw_z,sltc_class
   ```
   Lines starting with `#` are diagnostics, not samples.
5. **Drives the RGB LED:**

| LED | Meaning |
|---|---|
| Blue (PF2) | Heartbeat, toggles at 4 Hz while the loop is alive |
| Green (PF3) | Classified *smooth*, with confidence > 0.6 |
| Red (PF1) | Classified *turbulence*, with confidence > 0.6 |
| Red blinking at 1 Hz, no data | ADC never completed (fatal init error) |

The loop runs to a **fixed deadline** (`SAMPLE_PERIOD_MS = 10`, i.e. 100 Hz) instead of "work, then sleep", so the timebase doesn't drift. It counts overruns and reports them as `# overruns=…`.

### Boot diagnostics

Over UART the firmware prints a banner, the resting raw counts (expect ~2048 per axis and ~2876 on the vertical one), a warning if any axis is railed (the BoosterPack is probably not seated), and a warning if `SAMPLE_PERIOD_MS` disagrees with the `DT` baked into the weights.

### Build and flash

```bash
bash scripts/build_tiva.sh   # make clean && make all → tiva/hello_tiva.{elf,bin}
bash scripts/flash_tiva.sh   # lm4flash tiva/hello_tiva.bin
```

Or from `tiva/`: `make`, `make flash`, `make flash LMDEV=…` (when more than one board is connected), and `make clean`.

### Things that look wrong but are deliberate

- **`-O0`, not `-O2`.** This firmware hangs silently under `-O2` with this toolchain. Bisecting confirmed it, but the root cause is still open. Code size doesn't matter here (a few KB of 256 KB).
- **UART is initialised before SysTick.** The reverse order reliably hangs the board. Root cause not yet found.
- **`-MMD -MP` dependency tracking.** Without it, regenerating `sltc_weights.h` would *not* trigger a rebuild, and `make flash` would silently flash the old weights.
- **The accelerometer is analog, not I2C.** An earlier version targeted a BMI160 over I2C (kept as `main.cpp.i2c-bmi160.bak`). The EDU MKII has no BMI160.
- **Measured sensitivity is ~667 mV/g, not the ADXL326 datasheet's 57 mV/g.** Whatever part is fitted to this board revision is a low-g (~±2 g) device. Raw counts are logged, so you can recalibrate from a capture without reflashing. See the comment above `ACCEL_COUNTS_PER_G` in `main.cpp`.

---

## 5. The sLTC network

Each of the 4 hidden neurons is a liquid-time-constant integrator (Hasani et al., 2021) with a spiking output. The update for one timestep is:

```
x     = (x_raw - NORM_MEAN) / NORM_STD
drive = BIAS + W_IN·x + W_REC·s_prev
gate  = sigmoid(drive)
dh/dt = -h/TAU + gate·(A - h)          # effective time constant depends on the input
h    += DT · dh/dt
s     = h > V_TH                       # spike (V_TH = 1.0)
h    -= s · V_TH                       # soft reset
rate += RATE_ALPHA · (s - rate)        # EMA firing rate
logits = READOUT_W · rate + READOUT_B  # 0 = smooth, 1 = turbulence
```

### Input encodings

The training run picks the encoding and stamps it into `sltc_weights::ENCODING`. The firmware selects its encoder from that constant at compile time, so the board cannot feed the network a representation it wasn't trained on.

| `ENCODING` | Name | Channels | Description |
|---|---|---|---|
| 0 | absolute | 3 | Raw X/Y/Z in g, gravity included |
| 1 | delta-analog | 3 | `x[t] − x[t−1]` with a deadzone. Gravity cancels, so slow tilts are nearly invisible |
| 2 | delta-poisson | 6 | ON/OFF intensities per axis, Bernoulli-sampled into spikes (seeded xorshift32, so stochastic but reproducible) |
| 3 | delta-onoff | 6 | ON/OFF intensities per axis, graded and deterministic |

The delta encodings exist so the classifier can't "cheat" by learning which way is down.

### Train/deploy parity

`tiva/sltcneuron.hpp` must stay **bit-for-bit equivalent** to the training model's forward pass and `encode()`. That covers update order (all neurons read the *previous* step's spikes), the rate EMA, and the encoder. `tiva/test/encoder_parity.cpp` is a host-side harness that runs the firmware's real `InputEncoder` on stdin so it can be diffed against the Python encoder.

---

## 6. Data and training workflow

```bash
# 1. Flash the firmware (any weights are fine for recording; ignore the DT warning)
# 2. Record several varied takes of each class (~60 s each)
python3 scripts/record_dataset.py --label smooth     --seconds 60
python3 scripts/record_dataset.py --label turbulence --seconds 60
#    → data/<label>_NN.txt in the current directory

# 3. Train on the host and export the weights header
python3 training/train_sltc.py ... --export-cpp tiva/sltc_weights.h

# 4. Rebuild and reflash. The header change triggers a rebuild automatically
bash scripts/build_tiva.sh && bash scripts/flash_tiva.sh
```

**Recording guidance:**
- *smooth*: carry, tilt, rotate slowly, set down gently.
- *turbulence*: shake, tap, vibrate, jostle.
- Vary orientation in **both** classes, or the easiest feature becomes "which way is down".
- `record_dataset.py` prints a per-take summary that includes **mean jerk**. If jerk doesn't separate your two classes, training won't either. It warns when a smooth take is too jerky or a turbulence take too gentle.

**Serial tools:**

| Script | Transport | Use |
|---|---|---|
| `scripts/tiva_serial.py` | pyusb over usbfs | Shared module. Talks CDC-ACM directly because the container has no `CAP_MKNOD` to create `/dev/ttyACM0`. Detaches `cdc_acm` and reattaches it on exit |
| `scripts/read_tiva_serial.py` | via `tiva_serial` | Print or tee the raw stream: `--seconds 10 --out capture.csv` |
| `scripts/record_dataset.py` | via `tiva_serial` | Labelled, header-stamped recordings with stats |
| `training/read_serial.py` | pyserial on `/dev/ttyACM0` | Older host-only reader |

**Recorded data so far:** `scripts/data/` holds real 100 Hz takes with raw counts (`smooth_01`, `smooth_02`, `turbulence_01`). `training/data/` holds 20 Hz synthetic stand-ins from the first iteration of the training script, in the old 4-column format.

---

## 7. ROS2 (`ros2_ws/`)

```bash
bash scripts/build_ros2.sh     # colcon build --symlink-install
bash scripts/run_snn_hello.sh  # ros2 run snn_hello snn_hello_node
```

`snn_hello` is still a placeholder that logs a tick every second. A natural next step is a node that reads the UART stream and publishes samples and `sltc_class` as ROS2 topics. The container uses `network_mode: host`, so DDS multicast discovery works between nodes inside and outside the container.

---

## 8. Project layout

```
Tiva SNN/
├── Containerfile                # Ubuntu 22.04 + ARM toolchain + lm4flash + ROS2 Humble
├── compose.yaml                 # tiva-snn-dev service: bind mounts, USB passthrough, host network
├── README.md
│
├── tiva/                        # Bare-metal firmware (C++17, no TivaWare)
│   ├── main.cpp                 # ADC logger + fixed-rate loop + sLTC inference + LEDs
│   ├── sltcneuron.hpp           # InputEncoder + sLTCNeuron forward pass (must match training)
│   ├── sltc_weights.h           # GENERATED by train_sltc.py --export-cpp (committed: the build needs it)
│   ├── startup.c                # Vector table + reset handler
│   ├── tm4c123gh6pm.ld          # Linker script
│   ├── Makefile
│   └── test/encoder_parity.cpp  # Host harness: firmware encoder vs Python encode()
│
├── training/                    # Host-side (not mounted into the container)
│   ├── train_sltc.py            # PyTorch sLTC training + C++ header export
│   ├── read_serial.py           # pyserial stream reader
│   └── data/                    # Synthetic 20 Hz stand-ins
│
├── scripts/
│   ├── build_image.sh           # podman build via a /tmp symlink (space-in-path workaround)
│   ├── setup_usb_symlink.sh     # /dev/Tiva/LaunchPad → current usbfs node (runs at container start)
│   ├── build_tiva.sh / flash_tiva.sh
│   ├── build_ros2.sh / run_snn_hello.sh
│   ├── tiva_serial.py           # CDC-ACM over pyusb
│   ├── read_tiva_serial.py      # Dump or tee the UART stream
│   ├── record_dataset.py        # Labelled recordings
│   └── data/                    # Real 100 Hz recordings
│
└── ros2_ws/src/snn_hello/       # Placeholder ROS2 C++ node
```

`compose.yaml` bind-mounts `tiva/`, `ros2_ws/` and `scripts/` into `/workspace`, so host edits show up in the container immediately. `training/` is **not** mounted, because training runs on the host.

---

## 9. Known issues and TODO

- **`train_sltc.py` is behind `sltc_weights.h`.** The committed header was generated by a newer version of the script, with `--synthetic`, encodings, `RATE_ALPHA`, and 6 inputs. The script in the repo is the earlier version: 3 absolute inputs, a windowed-mean readout, no `ENCODING`/`RATE_ALPHA` export, and 4-column CSV parsing. **Re-exporting with the current script produces a header the firmware won't compile against.** Restore or re-port the newer script.
- **`training/verify_encoder.py` is missing.** `tiva/test/encoder_parity.cpp` refers to it as the driver that compiles the harness and diffs it against Python.
- **The current weights are placeholders**, trained on synthetic data. The LED classification means nothing until you retrain on `scripts/data/` recordings (100 Hz, matching `SAMPLE_PERIOD_MS`).
- **`pyusb` isn't installed in the image.** Add `pip3 install pyusb` to the Containerfile to run the recording scripts inside the container.
- **`compose.yaml` hardcodes USB bus `001`** and passes through `/dev/tiva_serial`. Adjust both to match your host (`lsusb`). Container start fails if `/dev/tiva_serial` doesn't exist.
- **`-O2` hang and UART/SysTick init order** are still not root-caused (see §4).
- More recordings are needed: currently 2 smooth takes and 1 turbulence take.

---

## 10. Notes

- **TivaWare is not used.** All peripheral access is direct memory-mapped register writes, which keeps the toolchain fully open-source.
- **Prefer the device mount over `--privileged`** for USB access, together with proper udev rules.
- **ROS2 DDS discovery** relies on UDP multicast, hence `network_mode: host`.
