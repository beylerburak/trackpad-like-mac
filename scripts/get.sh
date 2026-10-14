#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# One-line installer for trackpad-like-mac:
#
#   curl -fsSL https://raw.githubusercontent.com/beylerburak/trackpad-like-mac/main/scripts/get.sh | bash
#
# Downloads the latest release, checks it against the published SHA256SUMS
# and installs it: as a .deb on Debian/Ubuntu (amd64), otherwise from source.
set -euo pipefail

REPO=beylerburak/trackpad-like-mac

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run as your normal user; it asks for sudo when needed"
command -v curl >/dev/null || die "curl is required"

tag=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" |
    sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -n1)
[ -n "$tag" ] || die "could not find the latest release of $REPO"
version=${tag#v}
base="https://github.com/$REPO/releases/download/$tag"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"

echo "==> Downloading trackpad-like-mac $version"
curl -fsSLO "$base/SHA256SUMS"

if command -v apt-get >/dev/null && [ "$(dpkg --print-architecture)" = amd64 ]; then
    deb="trackpad-like-mac_${version}_amd64.deb"
    curl -fsSLO "$base/$deb"
    grep " $deb\$" SHA256SUMS | sha256sum -c --quiet || die "checksum mismatch for $deb"
    echo "==> Installing the package (asks for your password)"
    sudo apt-get install -y "./$deb"
    if [[ "${XDG_CURRENT_DESKTOP:-}" == *GNOME* ]]; then
        trackpad-like-mac setup
    fi
else
    tarball="trackpad-like-mac-$version.tar.gz"
    curl -fsSLO "$base/$tarball"
    grep " $tarball\$" SHA256SUMS | sha256sum -c --quiet || die "checksum mismatch for $tarball"
    tar -xzf "$tarball"
    "./trackpad-like-mac-$version/install.sh"
fi
