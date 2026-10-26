# Raspberry Pi DRO Parts and Printed Hardware

This list describes a standalone Pi host for the existing Pico 2 DRO. Prices and delivery estimates vary; Amazon links are live searches or product pages and should be checked before ordering.

## Electronics and Display

| Qty | Part | Selection notes | Link |
|---:|---|---|---|
| 1 | Raspberry Pi 4 Model B, 4 GB | Pi 4 is sufficient for the Pygame DRO. A Pi 5 also works. | [Amazon search: Raspberry Pi 4 Model B 4 GB](https://www.amazon.com/s?k=Raspberry+Pi+4+Model+B+4GB) |
| 1 | 7-inch HDMI touchscreen, 1024 x 600, USB touch | Use landscape orientation. HDMI is video; USB is touch. Prefer a panel with a separate 5 V input and mounting points or a measurable bezel for the adjustable printed clamp. | [Amazon search: 7-inch 1024x600 HDMI USB touchscreen](https://www.amazon.com/s?k=7+inch+1024x600+HDMI+USB+touchscreen) |
| 1 | microSD card, 32 GB or larger, A1/A2 | Raspberry Pi OS Desktop 64-bit. | [Amazon search: 32 GB A2 microSD](https://www.amazon.com/s?k=32GB+A2+microSD) |
| 1 | 5.1 V / 3 A USB-C supply for Pi 4 | Use a supply appropriate for the Pi 4 and peripherals. Do not power a high-draw display from the Pi unless its current rating allows it. | [Amazon search: Raspberry Pi 4 USB-C power supply](https://www.amazon.com/s?k=Raspberry+Pi+4+USB-C+power+supply+5.1V+3A) |
| 1 | Display power supply | Match the touchscreen maker's voltage/current requirement; many 7-inch panels need their own 5 V input. | Follow the exact display listing/manual |
| 1 | Short HDMI cable and USB-A-to-USB cable | HDMI for image; USB cable from touchscreen to Pi for touch events. | Match the selected screen's ports |
| 1 | USB data cable, Pi to Pico 2 | Keep the Pico connected in normal firmware mode. | USB cable matching the Pico 2 connector |

## Scales, Interfaces, and Sensor

| Qty | Part | Selection notes | Link |
|---:|---|---|---|
| 1 | DITRON 250 mm, 5 um optical scale for X | Listing identifies 5 um accuracy/resolution and standard TTL output; the product page says EIA-422 can be requested. Confirm electrical output and decoded counts before ordering. | [Amazon listing](https://www.amazon.com/dp/B0D4J3DS37) |
| 1 | DITRON 900 mm, 5 um optical scale for Z | Same family and stated output options as the 250 mm listing. Confirm it is the requested effective travel length. | [Amazon listing](https://www.amazon.com/dp/B0D4J4MF6Q) |
| 1 | TXS0108E 8-channel level-shifter board | Only for confirmed single-ended TTL output at the listed voltage levels. Use four channels for X/Z A/B; power low side from Pico 3.3 V and high side from regulated 5 V, with common ground. Test one axis at a time. It is not an EIA-422 receiver and is less robust than differential reception over long/noisy cables. | [Amazon listing, 5 boards](https://www.amazon.com/dp/B0FR4D3RV4) |
| 1 | DITRON alternative EIA-422 scale output | Ask the seller to supply EIA-422 if selected. In that case omit the TXS0108E and use differential RS-422 receiver circuitry/modules with 3.3 V logic outputs at the Pico end. | Contact DITRON before checkout |
| 1 | LJ12A3-4-Z/BX inductive tach sensor, NPN normally-open | Listing says 6-36 V supply and NPN NO. Power from the PC PSU 12 V rail. Confirm it is an open-collector/sinking output; only then may its black output use GP8's 3.3 V pull-up directly. | [Amazon single-sensor listing](https://www.amazon.com/dp/B07TMKTZ9L) |
| 1 | Raspberry Pi Pico 2 | Lathe X GP9/10, lathe Z GP11/12, mill X/Y/Z GP2/3, GP6/7, GP4/5; tach GP8. | Existing hardware |

**Electrical limits:** Pico GPIO must stay within 0-3.3 V. Never connect the PC PSU's 5 V or 12 V rail directly to a Pico GPIO. TTL scales require the specified logic interface. EIA-422 scales require differential receivers. Verify actual connector pinout, output swing, and signal grounds from the supplier documentation before wiring.

The app currently assumes 25,400 decoded counts per inch. The scale's “5 um” marking is not enough to infer the count convention. Calibrate each axis against a trusted standard in the DRO's SETUP screen and verify travel over a long distance.

## Printed Parts

The Fusion script `fusion_pi_mounts.py` generates separate printable bodies:

- A landscape screen backplate with retaining-strap slots and a captured 1/4-20 arm nut. Set the display's measured outside case width, height, and thickness in the script before running it.
- Zip-tie slots below the display to secure a vented commercial Raspberry Pi 4 case; this keeps its connector layout accessible.
- A Pico/TXS electronics enclosure base and lid with board tie-down slots, ventilation, and open cable-entry gaps at both ends.

Recommended printed materials: PETG or ASA, 4-5 perimeters and 35-50% infill. Avoid PLA in a warm machine enclosure. Test-fit screen corners, Pi port access, ventilation, cable bend radius, and arm clearance before final mounting.

### Printed-Part Hardware

- 1 x 1/4-20 hex nut for the screen arm hub.
- Two 15-20 mm hook-and-loop straps for the touchscreen slots.
- Two wide reusable zip ties or hook-and-loop straps for the Pi case.
- 4 x M3 screws/inserts for the electronics-box lid.
- Small cable glands or grommets sized to the selected scale cables.
- Thin rubber/TPU pads for screen contact points and a separate safety tether from the arm to the display cradle.

In Fusion, add `fusion_pi_mounts.py` from Scripts and Add-Ins and run it in a new design. Right-click each generated body and choose **Save as Mesh** to export separate STLs. Print the screen plate with the arm boss on the build plate and the box lid flat. Test-fit the measured display, Pi case, ports, cables, and arm clearance before final mounting.

## Boot Autostart

Use Raspberry Pi OS Desktop with desktop auto-login enabled. From the `raspberry_pi_dro` folder run:

```bash
bash install_pi.sh
sudo usermod -aG dialout "$USER"
```

Log out/in after changing group membership, then enable the per-user desktop autostart:

```bash
./enable_autostart.sh
```

In Raspberry Pi Configuration, set **System > Auto Login > Desktop Autologin** (wording varies by OS release), then reboot with the Pico attached in normal mode. The DRO starts after the graphical desktop launches. Remove `~/.config/autostart/lathe-dro.desktop` to disable autostart. This is not a headless system service; a visible Pygame touchscreen app requires the graphical session.
