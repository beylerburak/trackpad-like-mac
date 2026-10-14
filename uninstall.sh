#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Removes trackpad-like-mac and restores your previous touchpad settings.
# Same as running `trackpad-like-mac uninstall`.
set -euo pipefail

[ "$(id -u)" -ne 0 ] || { echo "error: run as your normal user: ./uninstall.sh" >&2; exit 1; }
command -v trackpad-like-mac >/dev/null || { echo "trackpad-like-mac is not installed." >&2; exit 1; }
exec trackpad-like-mac uninstall
