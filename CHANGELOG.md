# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-14

First release.

### Added

- Three-finger drag, with a short grace period to re-place your fingers.
  Pointing on with one finger ends the drag at once.
- GNOME's workspace and overview gestures moved to four fingers.
- Thumb-and-three-finger pinch for the app grid and spread for showing the
  desktop, with animations that follow the fingers.
- Two-finger swipe in from the right edge for notifications.
- Mac-like two-finger scrolling on Wayland: one-to-one when slow, faster when
  flicking, calibrated to the screen.
- Mac-like touchpad defaults: tap to click, no tap-and-drag, two-finger right
  click, natural scrolling.
- `trackpad-like-mac` command with `setup`, `reset`, `status` and `uninstall`.
- Debian package, one-line installer and source install.

[0.1.0]: https://github.com/beylerburak/trackpad-like-mac/releases/tag/v0.1.0
