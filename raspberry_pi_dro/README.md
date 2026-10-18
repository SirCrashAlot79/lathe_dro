# Raspberry Pi Lathe DRO

A separate Raspberry Pi host build of the Lathe DRO. It runs the existing Pygame interface fullscreen on Raspberry Pi OS Desktop and communicates with the same Pico 2 firmware over USB serial.

## Suggested Hardware

- Raspberry Pi 4 Model B, 4 GB RAM. The DRO is light enough for a Pi 4; a Pi 5 also works but is not required.
- 7-inch HDMI touchscreen with a landscape 1024 x 600 resolution, USB touch interface, and its own 5 V power input. HDMI carries the image; the USB cable carries touch events.
- 32 GB or larger A1/A2 microSD card.
- Official-quality 5.1 V / 3 A supply for a Pi 4. Use the supply specified by the display as well; do not assume the Pi USB port can power every panel.
- Case, cooling, short HDMI/USB cables, and a secure stand or arm mount for the display.
- Existing Raspberry Pi Pico 2 and a USB data cable from the Pi to the Pico.

The app's 1280 x 720 interface scales to the 1024 x 600 panel (roughly 1024 x 576 active UI with narrow top/bottom margins). The touchscreen is presented as a pointer device by Raspberry Pi OS; no app-specific touch driver is required.

## Install the Host App

1. Install the 64-bit Raspberry Pi OS Desktop image and complete first-boot setup. Use the graphical desktop, not Raspberry Pi OS Lite/headless, because the DRO needs a display session.
2. Copy this whole `raspberry_pi_dro` folder onto the Pi, for example to `~/lathe-dro/raspberry_pi_dro`.
3. From this directory run:

```bash
bash install_pi.sh
```

4. Add the desktop user to the serial-device group if needed, then log out and back in:

```bash
sudo usermod -aG dialout "$USER"
```

5. Connect the Pico 2 to a Pi USB port in normal firmware mode (not BOOTSEL), then start the DRO:

```bash
./run_dro.sh
```

The app auto-detects the Pico by USB vendor ID. If needed, identify the actual device and specify it, for example:

```bash
./run_dro.sh --port /dev/ttyACM0
```

Stop a foreground app with `Ctrl+C`. `./run_dro.sh --windowed` opens a 1280 x 720 window; `./run_dro.sh --demo --windowed` runs simulated values only.

To start automatically after the graphical desktop logs in, enable Desktop Autologin in Raspberry Pi Configuration, then run:

```bash
./enable_autostart.sh
```

Reboot with the Pico connected in normal firmware mode. The DRO starts after the desktop session and USB devices initialize. Disable it by removing `~/.config/autostart/lathe-dro.desktop`. This is not a headless service; Pygame needs the graphical session.

See [`PARTS_AND_PRINTING.md`](PARTS_AND_PRINTING.md) for the BOM and printed mounting/enclosure notes. The editable Fusion 360 script is [`fusion_pi_mounts.py`](fusion_pi_mounts.py).

## Pico Firmware

The host app expects the existing Pico 2 firmware packet `X:<count>,Z:<count>,RPM:<rpm>` over USB serial. You can flash the already-built `build-pico2/lathe_dro_pico.uf2` from a Windows PC as before.

To rebuild firmware on the Pi, install the ARM compiler and build tools, get the Pico SDK version used by this project, then build:

```bash
sudo apt install cmake ninja-build gcc-arm-none-eabi git python3
cd ~/lathe-dro/raspberry_pi_dro
git clone --branch 2.3.1 --recurse-submodules https://github.com/raspberrypi/pico-sdk.git pico-sdk
git -C pico-sdk submodule update --init --recursive
./build_pico2.sh
```

The UF2 will be generated at `build-pico2/lathe_dro_pico.uf2` within this folder.

## Scales and Sensor

- X A/B conditioned logic outputs go to Pico GP2/GP3; Z A/B go to GP4/GP5; spindle tach output goes to GP6.
- Pico GPIO must never exceed 0-3.3 V. The Ditron scale listing specifies standard TTL and offers EIA-422 by request; confirm which output was supplied. Use an appropriate interface for the actual output voltage/type before connecting it to the Pico.
- Keep each encoder A/B pair routed together, away from motor wiring. Join the interface signal ground to Pico ground only as required by that interface.
- The selected LJ12A3-4-Z/BX tach sensor is specified for a 6-36 V supply. If used, power it from the PC supply's 12 V rail (brown +, blue 0 V, black output per its listing). Confirm the NPN output is open-collector/sinking before using GP6's internal 3.3 V pull-up; never put 12 V on a GPIO.
- The firmware assumes 25,400 decoded counts per inch and four falling tach edges per revolution. Verify/calibrate these against the actual scales and target arrangement.

## Calibration and Per-Pi Data

Open `SETUP` on the DRO, select `INCH/MM`, enter a known physical linear travel, capture the start count for X or Z, move the axis, then apply calibration. Use actual radial cross-slide travel for X, even if the main readout is in DIA mode. Calibration factors are stored in `scale_calibration.json` beside this Pi copy of the app; tool touch-offs are stored in `tool_offsets.json` here as well. These files are separate from the Dell project's settings.

The first checkout and wiring should be tested with the spindle stopped. Verify each axis against a trusted standard and confirm RPM against a tachometer before relying on readings.
