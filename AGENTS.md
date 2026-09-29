# AGENTS.md

Guidance for AI coding agents working on this repo. Read `README.md` (usage)
and `NOTES.md` (full hardware investigation) first.

## User requirements (non-negotiable)

- **No third-party sources**: no PPAs, COPR, AUR, and **no one else's DialPad
  project** (e.g. `asus-linux-drivers/asus-dialpad-driver` on GitHub). Don't
  use, copy or read their code. Knowledge must come from the hardware itself,
  ACPI tables, the kernel, HID specifications, or **official ASUS/Microsoft
  material** (asus.com, the Microsoft Update Catalog).
- No extra packages on the system. The script is Python standard library
  only. Diagnostic tools (iasl, 7z, innoextract) were fetched as official
  Ubuntu `.deb`s with `apt-get download` and unpacked into a scratch directory,
  never installed.
- Reversible: `install.sh --uninstall` must remove everything.
- Don't write to the touchpad or to `ASUS2020` (feature/output reports)
  without understanding the command. Reading is fine.

## Key facts

- The PX13 DialPad is **software on top of the touchpad**; there's no dial
  hardware. ASUS's Windows filter attaches to `HID\ASCF1A03&Col02`.
- Geometry comes from ASUS INF `DIAL_LAYOUT_H75_*` (0.1 mm units). The
  touchpad is 124.2 × 75.7 mm by its HID descriptor, and evdev reports
  125.3 × 76.3 mm. `H75` = touchpad height 75 mm.
- Measured on real hardware: printed dial centre ≈ (17.3, 16.6) mm from the
  top-left, matching ASUS. Corner slides start at x ≈ 125 mm, so the switch
  box must reach the right edge.
- `ASUS2020` (i2c-3, 0x1D) is a standard radial-controller HID device that
  sends nothing on this model. It's probably for the physical ASUS Dial on
  other ProArts. Linux ignores it anyway: `IS_INPUT_APPLICATION` doesn't
  include 0x0001000e.
- The LED is set by `AsDrvLib_FUNC_VER1_CMD_LED_BrightLevel_Switch` via a
  touchpad feature report; the bytes are unknown. The user chose to skip the
  LED rather than disassemble `AsusDialPad.sys`. Ask before revisiting.

## Code map (`px13-dialpad.py`)

- Constants at the top are ASUS's values; keep the INF field numbers in the
  comments.
- `DialPad.frame()` runs once per `SYN_REPORT`: it classifies new touches
  (`switch`, `centre`, `dial`, `pad`), updates them, then `forward()`s
  non-consumed slots to the uinput clone while grabbed.
- The grab only toggles while no fingers are down, so libinput never sees a
  half-finished touch.
- `--debug` never grabs or emits. Use it to verify geometry changes on real
  hardware before anything else.
- Offline check without hardware: build `DialPad.__new__`, set the fields, and
  feed synthetic slots through `frame()` (this was done during development).

## Testing order

1. `python3 -m py_compile px13-dialpad.py`
2. Synthetic touches through `frame()` (no devices).
3. `sudo python3 px13-dialpad.py --debug` on the laptop.
4. `sudo python3 px13-dialpad.py` (Ctrl+C releases everything).
5. `sudo ./install.sh`, then suspend/resume, then reboot.

## Conventions

POSIX `sh` for `install.sh`; stdlib-only Python 3; MIT license; no AI
co-author trailers in commits.
