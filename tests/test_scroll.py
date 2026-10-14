"""Builds and runs the scroll shim's C tests (skipped without a C compiler)."""

import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent


@unittest.skipUnless(shutil.which("cc"), "needs a C compiler")
class ScrollShimTest(unittest.TestCase):
    def test_c_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = pathlib.Path(tmp) / "test_scroll"
            subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-o", str(binary),
                            str(HERE / "test_scroll.c"), "-ldl", "-lm"], check=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_library_builds_and_exports_only_the_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            library = pathlib.Path(tmp) / "libtrackpad-like-mac-scroll.so"
            source = HERE.parent / "src" / "scroll"
            subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-O2", "-shared", "-fPIC",
                            f"-Wl,--version-script={source / 'trackpad-like-mac-scroll.map'}",
                            "-o", str(library), str(source / "trackpad-like-mac-scroll.c"),
                            "-ldl", "-lm"], check=True)
            symbols = subprocess.run(["nm", "-D", "--defined-only", str(library)],
                                     capture_output=True, text=True, check=True).stdout
            exported = [line.split()[-1] for line in symbols.splitlines()
                        if " T " in line]
            self.assertEqual(exported,
                             ["libinput_event_pointer_get_scroll_value@@LIBINPUT_1.19"])


if __name__ == "__main__":
    unittest.main()
