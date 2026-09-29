# ASUS DialPad on the ProArt PX13 (HN7306): investigation notes

## Hardware

- Touchpad: FocalTech `ASCF1A03:00 2808:0357` on i2c-1, ACPI `\_SB.I2CB.ETPD`,
  bound to `hid-multitouch`. Size **124.2 × 75.7 mm**: HID X phys max 12420,
  Y 7567, unit cm, exponent −3. Logical max X 4010, Y 2443.
- `ASUS2020:00 0B05:0220` on i2c-3, address 0x1D, ACPI `\_SB.I2CD.DIDV`: a
  standard Microsoft Radial Controller descriptor (0x01/0x0E System
  Multi-Axis, Puck, Button 1, Dial −3600..3600, Resolution Multiplier).
  **It is not used for the PX13 DialPad**: zero interrupts while the dial
  gesture was performed. It's probably the physical ASUS Dial interface
  shared with other ProArt models. Linux creates no input device for it
  because `IS_INPUT_APPLICATION()` in `include/linux/hid.h` excludes
  0x0001000e.
- ACPI `\_SB.ATKD.DIAL(n)` is reached through ASUS WMI device ID
  `0x00100063`. It sets `DIBF` (default 2) and re-checks `DIDV`. Reading it
  returns 0x00010001 (present, enabled).

## How Windows does it (official sources)

The ASUS DialPad Driver is listed for HN7306EAC on asus.com as v24.0.0.21. The
asus.com installer is an encrypted Inno Setup package, so the files were taken
from the **Microsoft Update Catalog** instead: "ASUSTeK COMPUTER INC. HIDClass
Driver Update (24.0.0.22)", update ID `5aeffd34-102b-4837-9798-a65f4211c546`,
CAB SHA-1 `01aeb4059649ef6d165ce2d5414c68a4df45240f`. It contains:

- `AsusDialPadFilter.inf`: installs `AsusDialPad.sys` as a filter on
  `HID\ASCF1A03&Col02`, the touchpad's finger collection, plus
  `AsusDialPadService.exe`.
- The DialPad is **software**: the filter reads finger reports, detects the
  activation swipe, computes rotation, and lights the LED with a vendor
  feature-report command (`AsDrvLib_FUNC_VER1_CMD_LED_BrightLevel_Switch`;
  exact bytes unknown).

### Geometry for this touchpad: INF `DIAL_LAYOUT_H75_*` (units 0.1 mm)

| # | Meaning | Value |
|---|---|---|
| 00/01 | Dial centre X / Y | 173 / 166 |
| 02 | Radius | 150 |
| 03 | Inner radius | 55 |
| 04 | Tolerance | 177 |
| 05 | Control region type (0 circle, 1 rectangle) | 1 |
| 11–14 | Rect size T/B/L/R | 250/200/250/200 |
| 15/16 | Switch position X / Y | 1142 / 0 |
| 17/18 | Switch W / H | 100 / 120 |
| 19 | Edge tap | 50 |
| 21 | ROTATE_DIST_THRESHOLD | 49 |
| 22 | JITTER_DIST_THRESHOLD | 1 |
| 23 | SKIP_FRAME_THRESHOLD | 5 |
| 24 | DELTA_DIST_THRESHOLD | 38 |
| 30 | Report rate | 240 |

`DIAL_PARAM`: mixed mode 1 (touchpad keeps working outside the dial),
control mode 2 (tap+click), switch mode 2 ("dropdown" swipe), switch move
distance 150 (15 mm), tap 25 frames, long press 65 frames.

## Tools used (none installed on the system)

`iasl` (acpica-tools), `7z` (7zip), `innoextract`: official Ubuntu `.deb`s
extracted into a scratch directory with `apt-get download` + `dpkg-deb -x`.
