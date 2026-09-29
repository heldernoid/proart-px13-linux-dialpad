#!/usr/bin/env python3
"""Read-only capture of the ASUS DialPad (ASUS2020, 0B05:0220) and touchpad
(ASCF1A03, 2808:0357) HID traffic. Never writes to the devices.

    sudo ./capture.py [seconds]

Prints current feature-report values, then every input report received while
you try the DialPad gesture on the touchpad.
"""
import fcntl, glob, os, select, sys, time

DEVICES = {"0B05:0220": "dialpad", "2808:0357": "touchpad"}
FEATURES = {"dialpad": [0x01, 0x0A, 0x0B], "touchpad": [0x0B, 0x0E, 0x5D]}


def hidiocgfeature(size):
    # _IOC(_IOC_READ|_IOC_WRITE, 'H', 0x07, size)
    return (3 << 30) | (size << 16) | (ord("H") << 8) | 0x07


def find():
    found = {}
    for h in glob.glob("/sys/class/hidraw/hidraw*"):
        dev = os.path.basename(os.path.realpath(h + "/device"))  # 0018:0B05:0220.0003
        key = dev.split(":", 1)[1].split(".")[0]
        if key in DEVICES:
            found[DEVICES[key]] = "/dev/" + os.path.basename(h)
    return found


def irq_count(name):
    with open("/proc/interrupts") as f:
        for line in f:
            if name in line:
                return sum(int(x) for x in line.split()[1:] if x.isdigit())
    return None


def main():
    secs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    devs = find()
    fds = {}
    for name, path in devs.items():
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        fds[fd] = name
        print(f"{name}: {path}")
        for rid in FEATURES[name]:
            buf = bytearray(64)
            buf[0] = rid
            try:
                n = fcntl.ioctl(fd, hidiocgfeature(len(buf)), buf)
                print(f"  feature 0x{rid:02x}: {bytes(buf[:n]).hex(' ')}")
            except OSError as e:
                print(f"  feature 0x{rid:02x}: error {e}")

    irq0 = irq_count("ASUS2020")
    print(f"\nCapturing {secs}s. Try the DialPad: swipe diagonally from the small")
    print("circle at the top-right edge towards the bottom-left, check whether the")
    print("LED in the DialPad lights up, then circle your finger and tap it.\n")
    t0 = time.monotonic()
    counts = {}
    last = {}
    while time.monotonic() - t0 < secs:
        r, _, _ = select.select(list(fds), [], [], 0.5)
        for fd in r:
            data = os.read(fd, 256)
            name = fds[fd]
            rid = data[0]
            counts[(name, rid)] = counts.get((name, rid), 0) + 1
            # touchpad finger reports are very chatty: only print them when
            # the report id is new, print everything from the dialpad
            if name == "dialpad" or rid not in (0x01, 0x04) or last.get(rid) is None:
                print(f"{time.monotonic() - t0:7.3f} {name:8} {data.hex(' ')}")
            last[rid] = data
    print(f"\nDialPad (ASUS2020) interrupts during capture: {irq_count('ASUS2020') - irq0}")
    print("Report counts:")
    for (name, rid), n in sorted(counts.items()):
        print(f"  {name} report 0x{rid:02x}: {n}")


if __name__ == "__main__":
    main()
