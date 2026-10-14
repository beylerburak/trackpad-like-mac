"""Tests for the per-user setup command, with gsettings faked."""

import importlib.machinery
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "trackpad-like-mac"
_loader = importlib.machinery.SourceFileLoader("trackpad_like_mac_cli", str(_path))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
cli = importlib.util.module_from_spec(_spec)
_loader.exec_module(cli)


class FakeGsettings:
    def __init__(self):
        self.values = {
            (cli.SHELL, "enabled-extensions"): "['ding@rastersoft.com']",
            **{(cli.TOUCHPAD, key): "old" for key in cli.TOUCHPAD_SETTINGS},
        }

    def get(self, schema, key):
        return self.values[(schema, key)]

    def set(self, schema, key, value):
        self.values[(schema, key)] = value

    def extensions(self):
        return cli.parse_strv(self.values[(cli.SHELL, "enabled-extensions")])


class UserTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gsettings = FakeGsettings()
        self.user = cli.User(self.gsettings, pathlib.Path(self.tmp.name, "conf"))
        # No scroll library installed unless a test says so.
        patcher = mock.patch.object(cli, "LIBDIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def touchpad(self, key):
        return self.gsettings.get(cli.TOUCHPAD, key)


class UserTest(UserTestCase):
    def test_setup_enables_everything_and_remembers_old_settings(self):
        self.user.setup()
        self.assertEqual(self.gsettings.extensions(), ["ding@rastersoft.com", cli.UUID])
        self.assertEqual(self.touchpad("tap-and-drag"), "false")
        self.assertEqual(self.touchpad("click-method"), "'fingers'")
        self.assertEqual(self.user.state, "active")

        self.user.reset()
        self.assertEqual(self.gsettings.extensions(), ["ding@rastersoft.com"])
        self.assertTrue(all(self.touchpad(k) == "old" for k in cli.TOUCHPAD_SETTINGS))
        self.assertEqual(self.user.state, "reset")

    def test_setup_twice_keeps_the_original_settings(self):
        self.user.setup()
        self.user.setup()
        self.assertEqual(self.gsettings.extensions().count(cli.UUID), 1)
        self.user.reset()
        self.assertEqual(self.touchpad("speed"), "old")

    def test_login_sets_up_a_new_user(self):
        self.user.setup(at_login=True)
        self.assertEqual(self.user.state, "active")
        self.assertIn(cli.UUID, self.gsettings.extensions())

    def test_login_keeps_changes_made_after_setup(self):
        self.user.setup()
        self.gsettings.set(cli.TOUCHPAD, "speed", "0.6")  # changed in Settings
        self.user.setup(at_login=True)
        self.assertEqual(self.touchpad("speed"), "0.6")

    def test_login_after_reset_does_nothing(self):
        self.user.setup()
        self.user.reset()
        self.user.setup(at_login=True)
        self.assertNotIn(cli.UUID, self.gsettings.extensions())
        self.assertEqual(self.user.state, "reset")

    def test_setup_after_reset_turns_it_back_on(self):
        self.user.setup()
        self.user.reset()
        self.user.setup()
        self.assertIn(cli.UUID, self.gsettings.extensions())

    def test_scrolling_is_calibrated_for_the_screen(self):
        pathlib.Path(self.tmp.name, "libtrackpad-like-mac-scroll.so").touch()
        layout = [("HDMI-A-1", 1920, 1.0, False), ("eDP-1", 2560, 1.25, True)]
        with mock.patch.object(cli, "display_layout", return_value=layout), \
                mock.patch.object(cli, "panel_width_mm", return_value=366):
            self.user.setup()
        self.assertEqual(self.user.scroll_file.read_text(),
                         "px_per_mm=5.60 slow=1.0 fast=2.5\n")
        self.user.reset()
        self.assertFalse(self.user.scroll_file.exists())

    def test_scrolling_is_left_alone_without_the_library(self):
        with mock.patch.object(cli, "display_layout") as layout:
            self.user.setup()
        layout.assert_not_called()
        self.assertFalse(self.user.scroll_file.exists())

    def test_scrolling_is_left_alone_when_the_screen_is_unknown(self):
        pathlib.Path(self.tmp.name, "libtrackpad-like-mac-scroll.so").touch()
        with mock.patch.object(cli, "display_layout", side_effect=RuntimeError("no bus")), \
                mock.patch("sys.stderr"):
            self.user.setup()
        self.assertFalse(self.user.scroll_file.exists())
        self.assertEqual(self.user.state, "active")


class UninstallTest(UserTestCase):
    def run_recorder(self, package_installed):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            return mock.Mock(returncode=0 if package_installed else 1)
        return calls, run

    def test_removes_the_package(self):
        self.user.setup()
        calls, run = self.run_recorder(package_installed=True)
        cli.uninstall(self.user, run)
        self.assertIn(["sudo", "apt-get", "remove", "-y", "trackpad-like-mac"], calls)
        self.assertNotIn(cli.UUID, self.gsettings.extensions())

    def test_removes_files_listed_by_make_install(self):
        manifest = pathlib.Path(self.tmp.name, "installed-files")
        manifest.write_text("/usr/local/bin/trackpad-like-mac\n"
                            "/usr/local/share/gnome-shell/extensions/x/extension.js\n")
        calls, run = self.run_recorder(package_installed=False)
        cli.uninstall(self.user, run)
        self.assertIn(["sudo", "rm", "-f", "--", "/usr/local/bin/trackpad-like-mac",
                       "/usr/local/share/gnome-shell/extensions/x/extension.js"], calls)
        rmdir = next(c for c in calls if c[1] == "rmdir")
        self.assertEqual(rmdir[-2:], ["/usr/local/share/gnome-shell/extensions/x",
                                      "/usr/local/bin"])


class ScreenTest(unittest.TestCase):
    def test_prefers_the_builtin_screen(self):
        layout = [("DP-1", 3840, 1.0, False), ("eDP-1", 2560, 1.25, True)]
        widths = {"DP-1": 600, "eDP-1": 366}
        self.assertAlmostEqual(cli.screen_px_per_mm(layout, widths.get), 5.596, places=3)

    def test_falls_back_to_another_screen(self):
        layout = [("DP-1", 3840, 2.0, False)]
        self.assertAlmostEqual(cli.screen_px_per_mm(layout, lambda c: 600), 3.2)

    def test_unknown_size(self):
        self.assertIsNone(cli.screen_px_per_mm([("eDP-1", 2560, 1.0, True)], lambda c: None))

    def test_parse_strv(self):
        self.assertEqual(cli.parse_strv("@as []"), [])
        self.assertEqual(cli.parse_strv("['a', 'b']"), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
