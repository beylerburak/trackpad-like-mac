#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Installs trackpad-like-mac from this source tree into /usr/local and sets it
# up for the current user. Run as your normal user; it asks for sudo once.
# Undo with ./uninstall.sh.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run as your normal user (not with sudo): ./install.sh"
for tool in python3 systemctl make cc; do
    command -v "$tool" >/dev/null || die "$tool is required (on Ubuntu: sudo apt install build-essential python3)"
done
if dpkg -s trackpad-like-mac >/dev/null 2>&1; then
    die "the trackpad-like-mac package is already installed; remove it first (sudo apt remove trackpad-like-mac)"
fi

say "Building"
make --no-print-directory

say "Installing (asks for your password)"
sudo make --no-print-directory install
sudo modprobe uinput || true
sudo systemctl daemon-reload
sudo systemctl enable trackpad-like-mac.service
sudo systemctl restart trackpad-like-mac.service
systemctl --user daemon-reload || true

if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
    say "Setting up for $USER"
    /usr/local/bin/trackpad-like-mac setup
else
    say "Done"
    echo "Three-finger drag works now. The other gestures need GNOME Shell 45 or later."
fi
