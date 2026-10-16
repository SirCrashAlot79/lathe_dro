# Lathe DRO: Dell Latitude 7275 and Raspberry Pi Pico 2

The Dell runs the Pygame touchscreen readout; the Pico 2 reads the scales and spindle sensor and streams counts over USB serial.

## Dell: Ubuntu Server

Pygame needs a local graphical session. A headless SSH session alone cannot display the DRO. If the Server installation has no desktop, install a lightweight X session and touch input support:

```bash
sudo apt update
sudo apt install xserver-xorg xserver-xorg-input-libinput xinit openbox python3 python3-venv python3-pip
```

From the Dell's local console, create the Python environment and install the app dependencies:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x run_dro.sh build_pico2.sh
```

Add the login user to the serial-device group, then log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

If you installed Ubuntu Server without a display manager, start the kiosk session from a local text console:

```bash
cd /path/to/lathe-dro-project
printf 'exec %s/run_dro.sh\n' "$PWD" > ~/.xinitrc
startx
```

The DRO starts fullscreen by default on Linux. With an existing desktop, run `./run_dro.sh` from its terminal instead.

If the Pico is not auto-detected, pass its device path:

```bash
./run_dro.sh --port /dev/ttyACM0
```

For a windowed demo without the Pico:

```bash
./run_dro.sh --demo --windowed
```

## DRO Tools

- `FEED` looks up exact TPI values from the confirmed quick-change gearbox chart and displays the stud gear, tumbler, selector column, longitudinal feed, and cross feed. Feed per minute is estimated from the current spindle RPM; cross feed uses the chart plate's one-third ratio.
- `SPEED` estimates spindle RPM from work diameter and surface speed. Editable HSS starting presets are mild steel (80 SFM), aluminum (200 SFM), stainless steel (50 SFM), and cast iron (60 SFM). These are approximate starting points; the result is advisory only and does not control the spindle. Choose a safe speed available on the machine and verify it for the actual tool, material, workholding, and setup.
- `TAPER` calculates the compound-rest half-angle from large diameter, small diameter, and axial length.
- `COORD` calculates a midpoint, shoulder-to-shoulder distance, or up to 24 bolt-circle coordinates relative to the pattern center. Bolt-circle start angle is measured counterclockwise from +X.
- `TOOL SET` stores touch-off offsets in `tool_offsets.json` beside the Python app.

These calculators are references only; they do not control spindle, carriage, or cross-slide motion. They do not replace checking the machine's chart, tool manufacturer's guidance, or a test cut. Calibrate the scale counts per inch and verify the spindle RPM on the actual lathe before relying on displayed measurements or speed estimates.

The SPEED screen uses these operator-supplied spindle RPMs:

| Step | Belt, low | Back gear, low | Belt, high | Back gear, high* |
| --- | ---: | ---: | ---: | ---: |
| 1 (largest spindle pulley) | 240 | 50 | 460 | 90 |
| 2 (middle spindle pulley) | 410 | 78 | 780 | 155 |
| 3 (smallest spindle pulley) | 715 | 135 | 1365 | 265 |

The high-range back-gear column was marked with an asterisk in the supplied table; confirm its footnote before using those values. The screen chooses the highest listed speed not exceeding the target, and reports when the target is below the selected range.

## Pico 2 Firmware

Install the ARM compiler and build tools:

```bash
sudo apt install cmake ninja-build gcc-arm-none-eabi git python3
```

If `pico-sdk` is not already in the project directory, clone the SDK version used by this project, then initialize its dependencies:

```bash
git clone --branch 2.3.1 --recurse-submodules https://github.com/raspberrypi/pico-sdk.git pico-sdk
git -C pico-sdk submodule update --init --recursive
```

Build the Pico 2 image:

```bash
./build_pico2.sh
```

The UF2 image is written to `build-pico2/lathe_dro_pico.uf2`. Hold BOOTSEL while connecting the Pico 2 over USB, then copy the UF2 file to its mounted boot drive.

## Wiring and Calibration

- X scale channels A/B use GPIO 2/3.
- Z scale channels A/B use GPIO 4/5.
- The spindle sensor output uses GPIO 6.
- Keep Pico GPIO signals within 0-3.3 V; level-shift or condition scale and sensor outputs as required.
- The DRO currently assumes 25,400 scale counts per inch and four spindle sensor pulses per revolution. Verify these values against the installed scales and sensor before relying on measurements.
- Tool touch-offs are stored in `tool_offsets.json` beside the Python app. Capture T-1 at the reference datum, then capture each other tool at the same datum.