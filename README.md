# trackpad-like-mac

[![CI](https://github.com/beylerburak/trackpad-like-mac/actions/workflows/ci.yml/badge.svg)](https://github.com/beylerburak/trackpad-like-mac/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/beylerburak/trackpad-like-mac)](https://github.com/beylerburak/trackpad-like-mac/releases/latest)

Make your Linux touchpad feel like a MacBook trackpad: three-finger drag,
Mac gestures, and scrolling that sticks to your fingers.

[Türkçe](README.tr.md)

## What you get

| Gesture | What it does |
|---|---|
| Three-finger drag | Drags windows, files and text selections, like macOS "three-finger drag" |
| Four fingers left / right | Switches workspaces |
| Four fingers up / down | Opens / closes the overview (like Mission Control) |
| Pinch with thumb and three fingers | Opens the app grid (like Launchpad), following your fingers |
| Spread thumb and three fingers | Slides windows away to show the desktop; pinch to bring them back |
| Two fingers in from the right edge | Opens notifications; swipe right to close |
| Two-finger scroll | Content moves exactly as far as your fingers when slow, and speeds up when you flick |
| Tap | Click (tap-and-drag is off, so clicks never turn into accidental drags) |
| Two-finger click or tap | Right click |

Animations follow your fingers and snap back if you let go early, as on a Mac.

## Install

Log out and back in once after installing.

**One line** (Ubuntu, Debian and other distributions):

```bash
curl -fsSL https://raw.githubusercontent.com/beylerburak/trackpad-like-mac/main/scripts/get.sh | bash
```

It downloads the latest release, verifies its checksum and installs it: as a
`.deb` package on Debian/Ubuntu (amd64), from source elsewhere.

**Package** (Ubuntu/Debian): download the `.deb` from the
[latest release](https://github.com/beylerburak/trackpad-like-mac/releases/latest) and run

```bash
sudo apt install ./trackpad-like-mac_*_amd64.deb
```

**From source** (needs `make`, a C compiler and Python 3):

```bash
git clone https://github.com/beylerburak/trackpad-like-mac.git
cd trackpad-like-mac
./install.sh
```

## Requirements

- Linux with systemd and Python 3.9 or later
- GNOME Shell 45 to 48 for everything beyond three-finger drag (drag works on
  any desktop)
- A Wayland session for Mac-like scrolling
- A touchpad that reports at least four fingers (most do; see `trackpad-like-mac status`)

Developed and tested on Ubuntu 24.04 with GNOME 46 on Wayland.

## Usage

```bash
trackpad-like-mac status     # what is active
trackpad-like-mac reset      # turn it off for your user, restore your old touchpad settings
trackpad-like-mac setup      # turn it back on
trackpad-like-mac uninstall  # reset and remove everything
```

Every user is set up automatically at their first login. Changes you make
later in GNOME Settings are kept.

## Configuration

- `/etc/trackpad-like-mac.conf`: drag speed, how long a drag waits for your
  fingers to come back, and how far they move before it starts. Apply with
  `sudo systemctl restart trackpad-like-mac`.
- `~/.config/trackpad-like-mac/scroll.conf`: scrolling, applied instantly.
  `slow` and `fast` set how far content moves per finger millimetre when
  scrolling slowly and when flicking. `px_per_mm` is measured from your screen
  at each login.

## How it works

- **A small service** (`trackpad-like-mac-daemon`, Python, standard library
  only) reads the touchpad without taking it over. When three fingers move, it
  holds the button of a virtual mouse and follows them. It also tracks pinches
  and edge swipes on the raw touches, because libinput often mistakes a thumb
  for a resting finger, and streams them to the extension over a local socket.
  If the service stops, the touchpad keeps working normally.
- **A GNOME Shell extension** moves GNOME's built-in gestures from three to four
  fingers and drives the pinch and edge-swipe animations.
- **A tiny library** loaded only into GNOME Shell (Wayland session) rescales
  touchpad scrolling. libinput scrolls a fixed distance per finger millimetre
  on every screen, which on dense screens runs ahead of your fingers. GNOME
  does not offer a setting for this.

## Troubleshooting

- **The desktop doesn't start after installing**: on the login screen, click
  your name, choose "Ubuntu on Xorg" (or "GNOME on Xorg") from the gear menu and
  log in. The scrolling library is not loaded there. Then run
  `trackpad-like-mac uninstall` and
  [open an issue](https://github.com/beylerburak/trackpad-like-mac/issues).
- **A gesture doesn't work**: run `trackpad-like-mac status`, and check the
  service log with `journalctl -u trackpad-like-mac`.

## Limitations

- Force Touch and haptic feedback need Apple's hardware.
- libinput waits a few millimetres before it starts scrolling, and that can't
  be changed from outside.
- Scrolling is calibrated for the built-in screen; external monitors use the
  same ratio.
- Gestures other than drag are GNOME only for now.

## Development

```bash
make test   # run the tests
make        # build into build/
make deb    # build the Debian package into dist/
```

| Path | What it is |
|---|---|
| `src/trackpad-like-mac-daemon` | Drag, pinch and edge-swipe service |
| `src/trackpad-like-mac` | Per-user `setup` / `reset` / `status` / `uninstall` command |
| `src/scroll/` | Scrolling library for GNOME Shell |
| `extension/` | GNOME Shell extension |
| `data/` | systemd unit, autostart entry, default config |
| `packaging/deb/` | Debian package build |
| `scripts/get.sh` | One-line installer |

Releases are built by GitHub Actions when a `v*` tag is pushed. The tag must
match the version in `VERSION`, and the release notes come from `CHANGELOG.md`.

Contributions are welcome: please run `make test` and describe what you tested
on (distribution, GNOME version, touchpad).

## License

[GPL-3.0-or-later](LICENSE).

Not affiliated with Apple. Mac, MacBook and macOS are trademarks of Apple Inc.
