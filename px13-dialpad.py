#!/usr/bin/env python3
"""ASUS DialPad for the ProArt PX13 (HN7306) on Linux.

The DialPad is not a hardware dial: on Windows, ASUS's filter driver
(AsusDialPad.sys) reads the touchpad's finger positions and implements the
dial in software. This does the same with evdev + uinput, using the geometry
ASUS ships for this touchpad in AsusDialPadFilter.inf (DIAL_LAYOUT_H75_*).

    px13-dialpad.py            run (needs root: grabs the touchpad, uses uinput)
    px13-dialpad.py --debug    only print touches/dial events, change nothing

Standard library only.
"""
import argparse, errno, fcntl, glob, math, os, select, struct, subprocess, sys, time

TOUCHPAD_NAME = "ASCF1A03:00 2808:0357 Touchpad"

# ASUS INF DIAL_LAYOUT_H75_* / DIAL_PARAM_*, converted from 0.1 mm to mm.
# Coordinates are from the top-left corner of the touchpad.
DIAL_CX, DIAL_CY = 17.3, 16.6       # _00, _01
DIAL_R = 15.0                       # _02
DIAL_INNER_R = 5.5                  # _03 centre "button"
DIAL_START_MARGIN = 2.0             # accept touches just outside the ring
SWITCH_X, SWITCH_Y = 114.2, 0.0     # _15, _16
SWITCH_W, SWITCH_H = 10.0, 12.0     # _17, _18
SWITCH_MOVE = 15.0                  # DIAL_PARAM_03
ROTATE_STEP = 4.9                   # _21 ROTATE_DIST_THRESHOLD (arc length)
JITTER = 0.1                        # _22 JITTER_DIST_THRESHOLD
TAP_MAX_S = 0.30
TAP_MAX_MOVE = 2.0

MODES = ["Volume", "Brightness", "Scroll", "Zoom"]

# --- linux/input.h ---------------------------------------------------------
EV_SYN, EV_KEY, EV_REL, EV_ABS, EV_MSC = 0, 1, 2, 3, 4
SYN_REPORT, SYN_DROPPED = 0, 3
ABS_X, ABS_Y = 0x00, 0x01
ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y = 0x2F, 0x35, 0x36
ABS_MT_TOOL_TYPE, ABS_MT_TRACKING_ID = 0x37, 0x39
BTN_LEFT, BTN_RIGHT = 0x110, 0x111
BTN_TOOL_FINGER, BTN_TOOL_QUINTTAP, BTN_TOUCH = 0x145, 0x148, 0x14A
BTN_TOOL_DOUBLETAP, BTN_TOOL_TRIPLETAP, BTN_TOOL_QUADTAP = 0x14D, 0x14E, 0x14F
KEY_LEFTCTRL, KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP = 29, 113, 114, 115
KEY_BRIGHTNESSDOWN, KEY_BRIGHTNESSUP = 224, 225
REL_X, REL_Y, REL_WHEEL, REL_WHEEL_HI_RES = 0x00, 0x01, 0x08, 0x0B
BUS_VIRTUAL = 0x06

EVENT = struct.Struct("llHHi")
ABSINFO = struct.Struct("6i")


def _ioc(d, t, nr, size):
    return (d << 30) | (size << 16) | (ord(t) << 8) | nr


def EVIOCGNAME(n): return _ioc(2, "E", 0x06, n)
def EVIOCGPROP(n): return _ioc(2, "E", 0x09, n)
def EVIOCGBIT(ev, n): return _ioc(2, "E", 0x20 + ev, n)
def EVIOCGABS(a): return _ioc(2, "E", 0x40 + a, ABSINFO.size)
EVIOCGRAB = _ioc(1, "E", 0x90, 4)
UI_DEV_CREATE, UI_DEV_DESTROY = _ioc(0, "U", 1, 0), _ioc(0, "U", 2, 0)
UI_DEV_SETUP = _ioc(1, "U", 3, 92)
UI_ABS_SETUP = _ioc(1, "U", 4, 28)
UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT = (_ioc(1, "U", n, 4) for n in (100, 101, 102))
UI_SET_ABSBIT, UI_SET_MSCBIT, UI_SET_PROPBIT = (_ioc(1, "U", n, 4) for n in (103, 104, 110))


def log(*a):
    print("px13-dialpad:", *a, flush=True)


def bits(fd, req, nbytes):
    buf = bytearray(nbytes)
    fcntl.ioctl(fd, req, buf)
    return [i for i in range(nbytes * 8) if buf[i // 8] >> (i % 8) & 1]


def find_touchpad():
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        buf = bytearray(256)
        try:
            fcntl.ioctl(fd, EVIOCGNAME(len(buf)), buf)
        except OSError:
            os.close(fd)
            continue
        if buf.split(b"\0", 1)[0].decode(errors="replace") == TOUCHPAD_NAME:
            return fd, path
        os.close(fd)
    return None, None


class UInput:
    def __init__(self):
        self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)

    def setup(self, name, bustype, vendor, product, version=1):
        data = struct.pack("4H80sI", bustype, vendor, product, version,
                           name.encode()[:79], 0)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, data)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def emit(self, t, c, v):
        os.write(self.fd, EVENT.pack(0, 0, t, c, v))

    def syn(self):
        self.emit(EV_SYN, SYN_REPORT, 0)

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)


def clone_touchpad(src):
    """uinput copy of the touchpad; receives the non-dial touches while grabbed."""
    u = UInput()
    for ev in bits(src, EVIOCGBIT(0, 4), 4):
        fcntl.ioctl(u.fd, UI_SET_EVBIT, ev)
    for k in bits(src, EVIOCGBIT(EV_KEY, 96), 96):
        fcntl.ioctl(u.fd, UI_SET_KEYBIT, k)
    for m in bits(src, EVIOCGBIT(EV_MSC, 1), 1):
        fcntl.ioctl(u.fd, UI_SET_MSCBIT, m)
    for p in bits(src, EVIOCGPROP(4), 4):
        fcntl.ioctl(u.fd, UI_SET_PROPBIT, p)
    for a in bits(src, EVIOCGBIT(EV_ABS, 8), 8):
        fcntl.ioctl(u.fd, UI_SET_ABSBIT, a)
        info = bytearray(ABSINFO.size)
        fcntl.ioctl(src, EVIOCGABS(a), info)
        fcntl.ioctl(u.fd, UI_ABS_SETUP, struct.pack("HH", a, 0) + bytes(info))
    # same ids so libinput applies the same touchpad quirks
    info = bytearray(8)
    fcntl.ioctl(src, _ioc(2, "E", 0x02, 8), info)  # EVIOCGID
    bus, vid, pid, ver = struct.unpack("4H", info)
    u.setup(TOUCHPAD_NAME, bus, vid, pid, ver)
    return u


def dial_device():
    """Keys and wheel the dial emits."""
    u = UInput()
    for ev in (EV_KEY, EV_REL):
        fcntl.ioctl(u.fd, UI_SET_EVBIT, ev)
    for k in (KEY_LEFTCTRL, KEY_MUTE, KEY_VOLUMEDOWN, KEY_VOLUMEUP,
              KEY_BRIGHTNESSDOWN, KEY_BRIGHTNESSUP, BTN_LEFT, BTN_RIGHT):
        fcntl.ioctl(u.fd, UI_SET_KEYBIT, k)
    # REL_X/Y + BTN_LEFT make libinput treat it as a pointer, so wheel works
    for r in (REL_X, REL_Y, REL_WHEEL, REL_WHEEL_HI_RES):
        fcntl.ioctl(u.fd, UI_SET_RELBIT, r)
    u.setup("ASUS DialPad", BUS_VIRTUAL, 0x0B05, 0x0220)
    return u


class Notifier:
    """Desktop notification in the active user's session (we run as root)."""

    def __init__(self):
        self.last_id = 0

    def __call__(self, summary):
        for bus in glob.glob("/run/user/*/bus"):
            uid = int(bus.split("/")[3])
            if uid < 1000:
                continue
            try:
                import pwd
                user = pwd.getpwuid(uid).pw_name
                cmd = ["gdbus", "call", "--session",
                       "--dest", "org.freedesktop.Notifications",
                       "--object-path", "/org/freedesktop/Notifications",
                       "--method", "org.freedesktop.Notifications.Notify",
                       "DialPad", str(self.last_id), "input-dialpad-symbolic",
                       summary, "", "[]", "{'transient': <true>}", "1500"]
                if os.getuid() == 0:
                    cmd = ["runuser", "-u", user, "--", "env",
                           f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}"] + cmd
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=3).stdout
                digits = "".join(c for c in out if c.isdigit())
                if digits:
                    self.last_id = int(digits)
            except Exception:
                pass


class Slot:
    __slots__ = ("id", "x", "y", "tool", "kind", "x0", "y0", "t0",
                 "angle", "arc", "moved", "fired")

    def __init__(self):
        self.id, self.x, self.y, self.tool = -1, 0, 0, 0
        self.kind = None  # None | "dial" | "centre" | "switch" | "pad"


class DialPad:
    def __init__(self, fd, debug):
        self.fd, self.debug = fd, debug
        ax, ay = bytearray(ABSINFO.size), bytearray(ABSINFO.size)
        fcntl.ioctl(fd, EVIOCGABS(ABS_MT_POSITION_X), ax)
        fcntl.ioctl(fd, EVIOCGABS(ABS_MT_POSITION_Y), ay)
        _, self.xmin, self.xmax, _, _, self.xres = ABSINFO.unpack(ax)
        _, self.ymin, self.ymax, _, _, self.yres = ABSINFO.unpack(ay)
        nslots = bytearray(ABSINFO.size)
        fcntl.ioctl(fd, EVIOCGABS(ABS_MT_SLOT), nslots)
        self.slots = [Slot() for _ in range(ABSINFO.unpack(nslots)[2] + 1)]
        self.cur = 0
        self.button = 0
        self.pending = []           # MSC etc. to forward
        self.on = False
        self.grabbed = False
        self.want_grab = False
        self.mode = 0
        self.click_is_dial = False
        # state last sent to the clone
        self.out = [(-1, 0, 0, 0) for _ in self.slots]
        self.out_keys = {}
        self.out_xy = (None, None)
        self.clone = self.dev = None
        self.notify = Notifier()
        log(f"touchpad {self.mm(self.xmax, self.ymax)[0]:.1f} x "
            f"{self.mm(self.xmax, self.ymax)[1]:.1f} mm, {len(self.slots)} slots")
        if not debug:
            self.clone = clone_touchpad(fd)
            self.dev = dial_device()

    def mm(self, x, y):
        return (x - self.xmin) / self.xres, (y - self.ymin) / self.yres

    # --- geometry ---------------------------------------------------------
    @staticmethod
    def dial_polar(xm, ym):
        dx, dy = xm - DIAL_CX, ym - DIAL_CY
        return math.hypot(dx, dy), math.atan2(dy, dx)

    @staticmethod
    def in_switch(xm, ym):
        # ASUS's box is x 114.2-124.2, but this touchpad reports ~125.3 mm
        # wide and corner slides start right at the edge, so extend the box
        # to the right edge (and the top edge, y can be 0).
        return xm >= SWITCH_X and ym <= SWITCH_Y + SWITCH_H

    # --- actions ------------------------------------------------------------
    def toggle(self):
        self.on = not self.on
        log("dial", "ON" if self.on else "OFF", f"({MODES[self.mode]})")
        self.notify(f"DialPad on: {MODES[self.mode]}" if self.on else "DialPad off")
        if not self.debug:
            self.want_grab = self.on

    def next_mode(self):
        self.mode = (self.mode + 1) % len(MODES)
        log("mode", MODES[self.mode])
        self.notify(f"DialPad: {MODES[self.mode]}")

    def rotate(self, steps):
        log("rotate", steps, MODES[self.mode])
        if self.debug:
            return
        d, mode = self.dev, MODES[self.mode]
        for _ in range(abs(steps)):
            up = steps > 0  # clockwise
            if mode == "Volume":
                k = KEY_VOLUMEUP if up else KEY_VOLUMEDOWN
            elif mode == "Brightness":
                k = KEY_BRIGHTNESSUP if up else KEY_BRIGHTNESSDOWN
            else:
                k = None
            if k:
                d.emit(EV_KEY, k, 1); d.syn(); d.emit(EV_KEY, k, 0); d.syn()
            elif mode == "Scroll":  # clockwise scrolls down
                d.emit(EV_REL, REL_WHEEL, -1 if up else 1)
                d.emit(EV_REL, REL_WHEEL_HI_RES, -120 if up else 120)
                d.syn()
            elif mode == "Zoom":    # clockwise zooms in
                d.emit(EV_KEY, KEY_LEFTCTRL, 1)
                d.emit(EV_REL, REL_WHEEL, 1 if up else -1)
                d.emit(EV_REL, REL_WHEEL_HI_RES, 120 if up else -120)
                d.syn()
                d.emit(EV_KEY, KEY_LEFTCTRL, 0); d.syn()

    # --- per-touch logic ----------------------------------------------------
    def touch_start(self, s, now):
        xm, ym = self.mm(s.x, s.y)
        s.x0, s.y0, s.t0, s.moved, s.fired, s.arc = xm, ym, now, 0.0, False, 0.0
        r, a = self.dial_polar(xm, ym)
        s.angle = a
        if self.in_switch(xm, ym):
            s.kind = "switch"
        elif self.on and r <= DIAL_INNER_R:
            s.kind = "centre"
        elif self.on and r <= DIAL_R + DIAL_START_MARGIN:
            s.kind = "dial"
        else:
            s.kind = "pad"
        if self.debug:
            log(f"touch start ({xm:.1f}, {ym:.1f}) mm r={r:.1f} -> {s.kind}")

    def touch_move(self, s):
        xm, ym = self.mm(s.x, s.y)
        s.moved = max(s.moved, math.hypot(xm - s.x0, ym - s.y0))
        if s.kind == "switch" and not s.fired:
            dx, dy = xm - s.x0, ym - s.y0
            if math.hypot(dx, dy) >= SWITCH_MOVE and dx < 0 and dy > 0:
                s.fired = True
                self.toggle()
        elif s.kind in ("dial", "centre") and self.on:
            r, a = self.dial_polar(xm, ym)
            if r < 1.0:
                return
            da = (a - s.angle + math.pi) % (2 * math.pi) - math.pi
            arc = da * max(r, DIAL_INNER_R)
            if abs(arc) < JITTER:
                return
            s.angle = a
            if s.kind == "centre" and s.moved < TAP_MAX_MOVE:
                return  # still a tap candidate
            s.kind = "dial"
            s.arc += arc
            steps = int(s.arc / ROTATE_STEP)
            if steps:
                s.arc -= steps * ROTATE_STEP
                self.rotate(steps)

    def touch_end(self, s, now):
        if self.debug:
            log(f"touch end ({s.kind}) moved {s.moved:.1f} mm {now - s.t0:.2f} s")
        if (s.kind == "centre" and self.on and s.moved < TAP_MAX_MOVE
                and now - s.t0 <= TAP_MAX_S and not self.click_is_dial):
            self.next_mode()
        s.kind = None

    # --- evdev frame handling -------------------------------------------------
    def frame(self, now):
        for s in self.slots:
            if s.id >= 0 and s.kind is None:
                self.touch_start(s, now)
            elif s.id >= 0:
                self.touch_move(s)
            elif s.kind is not None:
                self.touch_end(s, now)
        consumed = lambda s: s.kind in ("dial", "centre", "switch")
        if self.button and not self.out_keys.get(BTN_LEFT) and not self.click_is_dial:
            fingers = [s for s in self.slots if s.id >= 0]
            if fingers and all(consumed(s) for s in fingers) and self.on:
                self.click_is_dial = True
                self.next_mode()
        if not self.button:
            self.click_is_dial = False
        if self.grabbed:
            self.forward(consumed)
        self.pending.clear()
        idle = all(s.id < 0 for s in self.slots) and not self.button
        if self.want_grab != self.grabbed and idle and not self.debug:
            fcntl.ioctl(self.fd, EVIOCGRAB, 1 if self.want_grab else 0)
            self.grabbed = self.want_grab
            log("touchpad", "grabbed" if self.grabbed else "released")

    def forward(self, consumed):
        c = self.clone
        active = []
        for i, s in enumerate(self.slots):
            want = (-1, 0, 0, 0) if s.id < 0 or consumed(s) else (s.id, s.x, s.y, s.tool)
            if want[0] >= 0:
                active.append(want)
            if want != self.out[i]:
                c.emit(EV_ABS, ABS_MT_SLOT, i)
                if want[0] != self.out[i][0]:
                    c.emit(EV_ABS, ABS_MT_TRACKING_ID, want[0])
                if want[0] >= 0:
                    c.emit(EV_ABS, ABS_MT_POSITION_X, want[1])
                    c.emit(EV_ABS, ABS_MT_POSITION_Y, want[2])
                    c.emit(EV_ABS, ABS_MT_TOOL_TYPE, want[3])
                self.out[i] = want
        n = len(active)
        keys = {BTN_TOUCH: int(n > 0), BTN_TOOL_FINGER: int(n == 1),
                BTN_TOOL_DOUBLETAP: int(n == 2), BTN_TOOL_TRIPLETAP: int(n == 3),
                BTN_TOOL_QUADTAP: int(n == 4), BTN_TOOL_QUINTTAP: int(n >= 5),
                BTN_LEFT: int(self.button and not self.click_is_dial)}
        for k, v in keys.items():
            if self.out_keys.get(k, 0) != v:
                c.emit(EV_KEY, k, v)
                self.out_keys[k] = v
        if active:
            xy = (active[0][1], active[0][2])
            if xy != self.out_xy:
                c.emit(EV_ABS, ABS_X, xy[0]); c.emit(EV_ABS, ABS_Y, xy[1])
                self.out_xy = xy
        for t, code, v in self.pending:
            c.emit(t, code, v)
        c.syn()

    def handle(self, t, code, v):
        if t == EV_ABS:
            s = self.slots[self.cur] if self.cur < len(self.slots) else None
            if code == ABS_MT_SLOT:
                self.cur = v
            elif s is None:
                pass
            elif code == ABS_MT_TRACKING_ID:
                s.id = v
            elif code == ABS_MT_POSITION_X:
                s.x = v
            elif code == ABS_MT_POSITION_Y:
                s.y = v
            elif code == ABS_MT_TOOL_TYPE:
                s.tool = v
        elif t == EV_KEY and code == BTN_LEFT:
            self.button = v
        elif t == EV_MSC:
            self.pending.append((t, code, v))
        elif t == EV_SYN and code == SYN_REPORT:
            self.frame(time.monotonic())
        elif t == EV_SYN and code == SYN_DROPPED:
            log("events dropped")

    def close(self):
        if self.grabbed:
            fcntl.ioctl(self.fd, EVIOCGRAB, 0)
        for u in (self.clone, self.dev):
            if u:
                u.close()


def run(debug):
    fd, path = find_touchpad()
    if fd is None:
        log(f"touchpad '{TOUCHPAD_NAME}' not found")
        return 1
    log("using", path, "(debug: nothing is grabbed or emitted)" if debug else "")
    pad = DialPad(fd, debug)
    try:
        while True:
            select.select([fd], [], [])
            try:
                data = os.read(fd, EVENT.size * 64)
            except OSError as e:
                if e.errno == errno.EAGAIN:
                    continue
                if e.errno == errno.ENODEV:
                    log("touchpad went away")
                    return 2
                raise
            for off in range(0, len(data), EVENT.size):
                _, _, t, code, v = EVENT.unpack_from(data, off)
                pad.handle(t, code, v)
    except KeyboardInterrupt:
        return 0
    finally:
        pad.close()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--debug", action="store_true",
                   help="print touches and dial events only; grab and emit nothing")
    a = p.parse_args()
    sys.exit(run(a.debug))


if __name__ == "__main__":
    main()
