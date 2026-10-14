# SPDX-License-Identifier: GPL-3.0-or-later
# trackpad-like-mac build, install and packaging.
#
#   make                 build into build/
#   make test            run the test suite
#   sudo make install    install under PREFIX (default /usr/local)
#   sudo make uninstall  remove what `make install` added
#   make deb             build a Debian/Ubuntu package into dist/
#   make dist            build a source tarball into dist/

NAME    := trackpad-like-mac
VERSION := $(shell cat VERSION)
UUID    := trackpad-like-mac@beylerburak.github.io

PREFIX             ?= /usr/local
SYSCONFDIR         ?= /etc
BINDIR             ?= $(PREFIX)/bin
LIBDIR             ?= $(PREFIX)/lib/$(NAME)
DATADIR            ?= $(PREFIX)/share
SYSTEMDUNITDIR     ?= $(PREFIX)/lib/systemd/system
SYSTEMDUSERUNITDIR ?= $(PREFIX)/lib/systemd/user
MODULESLOADDIR     ?= $(PREFIX)/lib/modules-load.d
AUTOSTARTDIR       ?= $(SYSCONFDIR)/xdg/autostart
EXTENSIONDIR       := $(DATADIR)/gnome-shell/extensions/$(UUID)
DOCDIR             := $(DATADIR)/doc/$(NAME)
SHELLDROPINDIR     := $(SYSTEMDUSERUNITDIR)/org.gnome.Shell@wayland.service.d

CC     ?= cc
CFLAGS ?= -O2 -Wall -Wextra

SUBST = sed -e 's|@LIBDIR@|$(LIBDIR)|g' -e 's|@BINDIR@|$(BINDIR)|g'

BUILT = build/libtrackpad-like-mac-scroll.so build/trackpad-like-mac \
        build/trackpad-like-mac.service build/gnome-shell-scroll.conf \
        build/trackpad-like-mac-setup.desktop

all: $(BUILT)

build:
	mkdir -p build

# Files with paths baked in are rebuilt whenever the paths change.
build/paths: FORCE | build
	@echo '$(LIBDIR) $(BINDIR)' | cmp -s - $@ || echo '$(LIBDIR) $(BINDIR)' > $@

build/libtrackpad-like-mac-scroll.so: src/scroll/trackpad-like-mac-scroll.c src/scroll/trackpad-like-mac-scroll.map | build
	$(CC) $(CFLAGS) -shared -fPIC -Wl,--version-script=src/scroll/trackpad-like-mac-scroll.map \
		-o $@ $< -ldl -lm

build/trackpad-like-mac: src/trackpad-like-mac build/paths
	$(SUBST) $< > $@
	chmod +x $@

build/%: data/%.in build/paths
	$(SUBST) $< > $@

test:
	python3 -m unittest discover -s tests

# Installed files, as "mode source destination".
INSTALLED = \
	755 src/trackpad-like-mac-daemon            $(LIBDIR)/trackpad-like-mac-daemon \
	644 build/libtrackpad-like-mac-scroll.so    $(LIBDIR)/libtrackpad-like-mac-scroll.so \
	755 build/trackpad-like-mac                 $(BINDIR)/trackpad-like-mac \
	644 build/trackpad-like-mac.service         $(SYSTEMDUNITDIR)/trackpad-like-mac.service \
	644 build/gnome-shell-scroll.conf           $(SHELLDROPINDIR)/trackpad-like-mac.conf \
	644 build/trackpad-like-mac-setup.desktop   $(AUTOSTARTDIR)/trackpad-like-mac-setup.desktop \
	644 data/modules-load.conf                  $(MODULESLOADDIR)/trackpad-like-mac.conf \
	644 extension/$(UUID)/extension.js          $(EXTENSIONDIR)/extension.js \
	644 extension/$(UUID)/metadata.json         $(EXTENSIONDIR)/metadata.json \
	644 README.md                               $(DOCDIR)/README.md \
	644 LICENSE                                 $(DOCDIR)/LICENSE
CONFIG    = $(SYSCONFDIR)/trackpad-like-mac.conf
# Lists what was installed, so `trackpad-like-mac uninstall` can remove it.
MANIFEST  = $(LIBDIR)/installed-files

install: all
	@set -e; set -- $(INSTALLED); while [ $$# -gt 0 ]; do \
		echo "install $$2 -> $$3"; install -Dm$$1 $$2 "$(DESTDIR)$$3"; shift 3; \
	done
	@# Keep a config the user already edited.
	test -e "$(DESTDIR)$(CONFIG)" || install -Dm644 data/trackpad-like-mac.conf "$(DESTDIR)$(CONFIG)"
	@set -- $(INSTALLED); while [ $$# -gt 0 ]; do echo "$$3"; shift 3; done \
		> "$(DESTDIR)$(MANIFEST)"
	echo "$(CONFIG)" >> "$(DESTDIR)$(MANIFEST)"
	echo "$(MANIFEST)" >> "$(DESTDIR)$(MANIFEST)"

uninstall:
	@set -- $(INSTALLED); while [ $$# -gt 0 ]; do rm -f "$(DESTDIR)$$3"; shift 3; done
	rm -f "$(DESTDIR)$(CONFIG)" "$(DESTDIR)$(MANIFEST)"
	-rmdir "$(DESTDIR)$(LIBDIR)" "$(DESTDIR)$(SHELLDROPINDIR)" "$(DESTDIR)$(EXTENSIONDIR)" \
		"$(DESTDIR)$(DOCDIR)" 2>/dev/null

deb:
	packaging/deb/build-deb.sh $(VERSION)

dist:
	mkdir -p dist
	git archive --format=tar.gz --prefix=$(NAME)-$(VERSION)/ \
		-o dist/$(NAME)-$(VERSION).tar.gz HEAD

clean:
	rm -rf build dist

.PHONY: all test install uninstall deb dist clean FORCE
