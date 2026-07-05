# BMO — Raspberry Pi GPIO Pinout

Applies to: RPi 4, RPi 5, Zero 2W (identical 40-pin header, same BCM numbering).

> **Pi 5 note:** change `lgpio.gpiochip_open(0)` → `lgpio.gpiochip_open(4)` in all scripts
> (RP1 GPIO controller lives at `/dev/gpiochip4`). Everything else is identical.

---

## Full 40-Pin Header

| Phys | BCM | Alt Function | Assignment                  | Peripheral                            |
| ---: | --: | :----------- | :-------------------------- | :------------------------------------ |
|    1 |   — | 3.3 V        | **3.3 V power**             | power rail                            |
|    2 |   — | 5 V          | **5 V power**               | power rail                            |
|    3 |   2 | I2C1 SDA     | I2C SDA                     | GT911 touch + MCP23017 SDA            |
|    4 |   — | 5 V          | **5 V power**               | power rail                            |
|    5 |   3 | I2C1 SCL     | I2C SCL                     | GT911 touch + MCP23017 SCL            |
|    6 |   — | GND          | **GND**                     |                                       |
|    7 |   4 | —            | M4 DIR                      | TMC2209 #4 direction                  |
|    8 |  14 | UART TXD     | *(spare / TMC2209 UART)*    | see note                              |
|    9 |   — | GND          | **GND**                     |                                       |
|   10 |  15 | UART RXD     | MCP23017 INT_A              | button interrupt                      |
|   11 |  17 | —            | Touch INT                   | GT911 interrupt                       |
|   12 |  18 | PCM_CLK      | I2S BCLK                    | amp + mic bit clock                   |
|   13 |  27 | —            | Touch RST                   | GT911 reset                           |
|   14 |   — | GND          | **GND**                     |                                       |
|   15 |  22 | —            | M3 STEP                     | TMC2209 #4 step                       |
|   16 |  23 | —            | M1 DIR                      | TMC2209 #3 direction *(demo default)* |
|   17 |   — | 3.3 V        | **3.3 V power**             | power rail                            |
|   18 |  24 | —            | LCD DC                      | ST7796S data/command                  |
|   19 |  10 | SPI0 MOSI    | LCD MOSI                    | ST7796S SPI data                      |
|   20 |   — | GND          | **GND**                     |                                       |
|   21 |   9 | SPI0 MISO    | LCD MISO                    | ST7796S SPI read-back                 |
|   22 |  25 | —            | LCD RST                     | ST7796S reset                         |
|   23 |  11 | SPI0 SCLK    | LCD SCLK                    | ST7796S SPI clock                     |
|   24 |   8 | SPI0 CE0     | LCD CS                      | ST7796S chip-select                   |
|   25 |   — | GND          | **GND**                     |                                       |
|   26 |   7 | SPI0 CE1     | Motors nEN (shared)         | TMC2209 #1–4 enable, active-LOW       |
|   27 |   0 | ID_SD        | *(HAT EEPROM — do not use)* |                                       |
|   28 |   1 | ID_SC        | *(HAT EEPROM — do not use)* |                                       |
|   29 |   5 | —            | M2 STEP                     | TMC2209 #3 step                       |
|   30 |   — | GND          | **GND**                     |                                       |
|   31 |   6 | —            | M2 DIR                      | TMC2209 #2 direction                  |
|   32 |  12 | PWM0         | M4 STEP                     | TMC2209 #2 step                       |
|   33 |  13 | PWM1         | LCD BL                      | ST7796S backlight (hardware PWM)      |
|   34 |   — | GND          | **GND**                     |                                       |
|   35 |  19 | PCM_FS       | I2S LRCK/WS                 | amp + mic frame sync                  |
|   36 |  16 | —            | M1 STEP                     | TMC2209 #1 step *(demo default)*      |
|   37 |  26 | —            | M3 DIR                      | TMC2209 #1 direction                  |
|   38 |  20 | PCM_DIN      | I2S DIN                     | mic data → Pi                         |
|   39 |   — | GND          | **GND**                     |                                       |
|   40 |  21 | PCM_DOUT     | I2S DOUT                    | Pi → amp data                         |

---

## Peripheral Details

### Waveshare 3.5" LCD — ST7796S (SPI) + GT911 (I2C)

| Signal     | BCM | Phys |
|------------|:---:|:----:|
| SPI SCLK   | 11  | 23   |
| SPI MOSI   | 10  | 19   |
| SPI MISO   | 9   | 21   |
| SPI CS     | 8   | 24   |
| DC         | 24  | 18   |
| RST        | 25  | 22   |
| BL (PWM1)  | 13  | 33   |
| Touch SDA  | 2   | 3    |
| Touch SCL  | 3   | 5    |
| Touch INT  | 17  | 11   |
| Touch RST  | 27  | 13   |

> **BL conflict warning:** the stock Waveshare overlay binds BL to GPIO18.
> Patch it to GPIO13 before use — GPIO18 is needed for I2S BCLK.

---

### I2S Audio (speaker/amp + microphone)

| Signal       | BCM | Phys | Connects to                     |
|--------------|:---:|:----:|---------------------------------|
| BCLK         | 18  | 12   | amp BCLK + mic SCK              |
| LRCK / WS    | 19  | 35   | amp LRC + mic WS                |
| DOUT → amp   | 21  | 40   | MAX98357A DIN (or PCM5102 DATA) |
| DIN ← mic    | 20  | 38   | INMP441 SD / SPH0645 DOUT       |

---

### Four TMC2209 Stepper Drivers

All four `ENN` pads wired together to GPIO7 (nEN shared).
GPIO7 HIGH = all drivers disabled (safe power-on default).
GPIO7 LOW  = all drivers enabled.

| Motor       | STEP BCM | STEP Phys | DIR BCM | DIR Phys | nEN BCM | nEN Phys |
|-------------|:--------:|:---------:|:-------:|:--------:|:-------:|:--------:|
| M1 *(demo)* | 16       | 36        | 23      | 16       | 7       | 26       |
| M2          | 5        | 29        | 6       | 31       | 7       | 26       |
| M3          | 22       | 15        | 26      | 37       | 7       | 26       |
| M4          | 12       | 32        | 4       | 7        | 7       | 26       |

TMC2209 power wiring (per driver):
- `VM` + its `GND` → motor PSU (12–24 V)
- `VIO` → 3.3 V
- `MS1` + `MS2` → 3.3 V (selects 16× microstepping in standalone mode)
- `A1 A2 B1 B2` → motor coils

---

### MCP23017 I2C GPIO Expander (7 buttons)

Sits on the same I2C1 bus as the GT911 touch controller.

| Signal   | Notes                                                                   |
|----------|-------------------------------------------------------------------------|
| SDA      | GPIO2, shared with GT911                                                |
| SCL      | GPIO3, shared with GT911                                                |
| I2C addr | `0x20` (A0 = A1 = A2 = GND) — no conflict with GT911 at `0x5D` / `0x14` |
| VDD      | 3.3 V                                                                   |
| INT\_A   | GPIO15 (pin 10) — interrupt line, no polling needed                     |
| GPA0–GPA6 | 7 button inputs; enable internal pull-ups in firmware                  |
| GPA7, GPB0–GPB7 | spare (future expansion)                                         |

---

### GPIO14 (pin 8) — Spare / Optional TMC2209 UART

Left unassigned. Optional use: connect to `PDN_UART` on all four TMC2209s
(1 kΩ series resistor; configure per-driver UART addresses) for runtime
current and microstepping control. Requires disabling the serial console
in `raspi-config → Interface Options → Serial Port`.
