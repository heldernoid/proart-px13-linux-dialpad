#!/bin/sh
# ASUS ProArt PX13 (HN7306) DialPad for Linux.
#
#   sudo ./install.sh              install / update (idempotent)
#   sudo ./install.sh --uninstall  remove everything this script installed
#   sudo ./install.sh --force      skip the hardware check
#
# Installs one Python script (standard library only) and a systemd service.
# No packages, no kernel changes.
set -eu

LIBDIR=/usr/local/lib/px13-dialpad
UNIT=px13-dialpad.service
SRC=$(cd "$(dirname "$0")" && pwd)
TOUCHPAD="ASCF1A03:00 2808:0357 Touchpad"

log() { echo "==> $*"; }
die() { echo "error: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run as root: sudo $0 $*"

uninstall() {
	log "stopping and removing $UNIT"
	systemctl disable --now "$UNIT" 2>/dev/null || true
	rm -f "/etc/systemd/system/$UNIT"
	systemctl daemon-reload
	rm -rf "$LIBDIR"
	log "uninstalled"
}

FORCE=0
case "${1:-}" in
	--uninstall) uninstall; exit 0 ;;
	--force) FORCE=1 ;;
	"") ;;
	*) die "unknown option $1" ;;
esac

if [ $FORCE = 0 ]; then
	grep -q "^N: Name=\"$TOUCHPAD\"" /proc/bus/input/devices ||
		die "touchpad '$TOUCHPAD' not found (not a PX13 HN7306?); --force to override"
fi
command -v python3 >/dev/null || die "python3 missing"
[ -c /dev/uinput ] || modprobe uinput || die "no /dev/uinput"

log "installing $LIBDIR/px13-dialpad.py"
install -d "$LIBDIR"
install -m 755 "$SRC/px13-dialpad.py" "$LIBDIR/px13-dialpad.py"

log "installing $UNIT"
install -m 644 "$SRC/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl enable "$UNIT" >/dev/null
systemctl restart "$UNIT"

sleep 1
systemctl is-active --quiet "$UNIT" || die "service failed: journalctl -u $UNIT"
log "done. Slide from the top-right corner of the touchpad towards the bottom-left to turn the DialPad on/off."
