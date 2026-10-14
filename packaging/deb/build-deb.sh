#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Builds dist/trackpad-like-mac_<version>_<arch>.deb from the source tree.
set -euo pipefail
cd "$(dirname "$0")/../.."

version=${1:?usage: build-deb.sh VERSION}
arch=$(dpkg --print-architecture)
root=$(mktemp -d)
chmod 755 "$root"  # becomes the package's "./"; must not be 0700
trap 'rm -rf "$root"' EXIT

make --no-print-directory install DESTDIR="$root" PREFIX=/usr >/dev/null

mkdir -p "$root/DEBIAN" dist
installed_kb=$(du -sk "$root" | cut -f1)
sed -e "s/@VERSION@/$version/" -e "s/@ARCH@/$arch/" -e "s/@SIZE@/$installed_kb/" \
    packaging/deb/control.in > "$root/DEBIAN/control"
# Every file under /etc must be a conffile.
(cd "$root" && find etc -type f | sed 's|^|/|' | sort) > "$root/DEBIAN/conffiles"
install -m755 packaging/deb/postinst packaging/deb/prerm packaging/deb/postrm "$root/DEBIAN/"

out="dist/trackpad-like-mac_${version}_${arch}.deb"
dpkg-deb --root-owner-group --build "$root" "$out" >/dev/null
echo "$out"
