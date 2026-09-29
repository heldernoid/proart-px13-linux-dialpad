# ASUS DialPad on Linux: ProArt PX13 (HN7306)

Makes the virtual **ASUS DialPad** printed on the ProArt PX13 / GoPro Edition
touchpad work on Linux. No PPA, no third-party code, no kernel changes: one
Python script using only the standard library, plus a systemd service.

Tested: Ubuntu 26.04.1, kernel 7.0.0-34-generic, HN7306EAC.

## Using it

| Gesture | Action |
|---|---|
| Slide from the small circle at the **top-right** towards the bottom-left | DialPad on/off (notification shows the mode) |
| Circle a finger on the printed **dial** (top-left) | Rotate: clockwise = up/next, counter-clockwise = down |
| Tap the centre of the dial (or click on it) | Next mode: Volume → Brightness → Scroll → Zoom |

While the DialPad is on, the rest of the touchpad keeps working normally.
Only touches that start on the dial or the switch corner are used by it.

## Install

```sh
sudo ./install.sh              # installs and starts px13-dialpad.service
sudo ./install.sh --uninstall  # removes it
```

It installs `/usr/local/lib/px13-dialpad/px13-dialpad.py` and
`/etc/systemd/system/px13-dialpad.service`, nothing else.

Try it without installing, or debug it:

```sh
sudo python3 px13-dialpad.py --debug   # only prints touches and dial events
sudo python3 px13-dialpad.py           # the real thing, Ctrl+C to stop
journalctl -u px13-dialpad -f          # logs of the installed service
```

## How it works

The DialPad has **no hardware of its own**. On Windows, ASUS's
"ASUS DialPad Driver" (a filter driver on the touchpad) reads raw finger
positions and implements the dial in software. This does the same:

1. Reads the touchpad (`ASCF1A03:00 2808:0357`) through evdev.
2. When the corner slide is detected, it grabs the touchpad and forwards every
   touch that isn't on the dial to a virtual copy of the touchpad (uinput), so
   pointing, tapping and gestures keep working.
3. Turns rotation on the dial into volume/brightness keys, scroll-wheel or
   Ctrl+wheel events from a virtual "ASUS DialPad" device, so GNOME shows its
   normal on-screen indicators.
4. On turning off, it releases the touchpad.

Dial position, size, switch area, activation distance and rotation step are
ASUS's own values for this touchpad (`DIAL_LAYOUT_H75_*` in ASUS's signed
`AsusDialPadFilter.inf`), converted to millimetres. The only change: the switch
area extends to the touchpad's right edge, because this unit reports 125.3 mm
wide and corner slides start at the very edge. See `NOTES.md` for the full
investigation.

If the service crashes, the grab is released automatically when the process
exits, so the touchpad can't stay stuck.

## Not supported yet

- **The LED** inside the dial: ASUS lights it with a vendor HID command that
  isn't documented anywhere readable.
- Per-application functions (ASUS ProArt Creator Hub) and on-screen dial menu.
- The separate `ASUS2020` radial-controller device (see `NOTES.md`); it isn't
  used by the PX13 DialPad.

## License

MIT, see `LICENSE`.
