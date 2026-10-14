"""Tests for the drag daemon's event decoding and state machine.

Run with: python3 -m unittest discover tests
"""

import importlib.machinery
import importlib.util
import pathlib
import select
import socket
import tempfile
import unittest

_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "trackpad-like-mac-daemon"
_loader = importlib.machinery.SourceFileLoader("trackpad_like_mac_daemon", str(_path))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
drag = importlib.util.module_from_spec(_spec)
_loader.exec_module(drag)


class FakeMouse:
    def __init__(self):
        self.pressed = False
        self.log = []
        self.moved = [0, 0]

    def press(self):
        self.pressed = True
        self.log.append("press")

    def release(self):
        if self.pressed:
            self.log.append("release")
        self.pressed = False

    def move(self, dx, dy):
        self.moved[0] += dx
        self.moved[1] += dy


def make_engine(**kwargs):
    mouse = FakeMouse()
    return drag.DragEngine(mouse, **kwargs), mouse


class DragEngineTest(unittest.TestCase):
    def test_three_finger_move_drags_and_release_waits_for_delay(self):
        engine, mouse = make_engine(release_delay=0.25)
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 2.0, 0, now=0.01)  # past the 1 mm threshold
        self.assertTrue(mouse.pressed)
        engine.frame(3, 10.0, 5.0, now=0.02)
        self.assertEqual(mouse.moved, [120, 60])

        engine.frame(0, 0, 0, now=0.03)
        engine.tick(0.2)
        self.assertTrue(mouse.pressed, "released before the grace period")
        engine.tick(0.3)
        self.assertFalse(mouse.pressed)
        self.assertEqual(engine.deadline(), None)

    def test_three_finger_tap_does_not_press(self):
        engine, mouse = make_engine()
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 0.2, 0.1, now=0.05)
        engine.frame(0, 0, 0, now=0.1)
        engine.tick(1.0)
        self.assertEqual(mouse.log, [])

    def test_replacing_fingers_within_delay_continues_drag(self):
        engine, mouse = make_engine(release_delay=0.25)
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 5.0, 0, now=0.01)
        engine.frame(0, 0, 0, now=0.02)
        engine.frame(3, 0, 0, now=0.1)
        engine.tick(0.5)
        engine.frame(3, 1.0, 0, now=0.5)
        self.assertEqual(mouse.log, ["press"])
        self.assertTrue(mouse.pressed)

    def start_drag(self, engine):
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 5.0, 0, now=0.01)

    def test_pointing_with_one_finger_after_drag_releases_at_once(self):
        engine, mouse = make_engine(release_delay=0.25)
        self.start_drag(engine)
        engine.frame(1, 0, 0, now=0.02)
        self.assertTrue(mouse.pressed)
        engine.frame(1, 0.4, 0.4, now=0.03)  # the finger moves on
        self.assertFalse(mouse.pressed)

    def test_one_finger_resting_after_drag_releases_after_grace(self):
        engine, mouse = make_engine(release_delay=0.25)
        self.start_drag(engine)
        engine.frame(1, 0, 0, now=0.02)
        engine.tick(0.09)
        self.assertTrue(mouse.pressed)
        engine.tick(0.11)
        self.assertFalse(mouse.pressed)

    def test_lifting_fingers_one_by_one_keeps_release_delay(self):
        engine, mouse = make_engine(release_delay=0.25)
        self.start_drag(engine)
        engine.frame(2, 0.1, 0, now=0.02)
        engine.frame(1, 0.1, 0, now=0.03)
        engine.frame(0, 0, 0, now=0.04)
        engine.tick(0.2)
        self.assertTrue(mouse.pressed, "drag ended before the release delay")
        engine.frame(1, 0, 0, now=0.21)  # fingers land one by one again
        engine.frame(3, 0, 0, now=0.22)
        engine.tick(0.5)
        self.assertTrue(mouse.pressed)
        self.assertEqual(mouse.log, ["press"])

    def test_one_finger_landing_during_release_delay_ends_drag(self):
        engine, mouse = make_engine(release_delay=0.25)
        self.start_drag(engine)
        engine.frame(0, 0, 0, now=0.02)
        engine.frame(1, 0, 0, now=0.1)
        engine.frame(1, 0.6, 0, now=0.11)
        self.assertFalse(mouse.pressed)

    def test_four_finger_swipe_never_drags(self):
        engine, mouse = make_engine()
        engine.frame(4, 0, 0, now=0.0)
        engine.frame(4, 20.0, 0, now=0.1)
        # Fingers lift one at a time after the swipe.
        engine.frame(3, 5.0, 0, now=0.2)
        engine.frame(3, 5.0, 0, now=0.21)
        engine.frame(2, 0, 0, now=0.22)
        engine.frame(0, 0, 0, now=0.23)
        self.assertEqual(mouse.log, [])

    def test_fourth_finger_ends_drag_immediately(self):
        engine, mouse = make_engine()
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 5.0, 0, now=0.01)
        engine.frame(4, 0, 0, now=0.02)
        self.assertEqual(mouse.log, ["press", "release"])

    def test_fractional_motion_accumulates(self):
        engine, mouse = make_engine()
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 2.0, 0, now=0.01)
        for i in range(10):
            engine.frame(3, 0.05, 0, now=0.02 + i * 0.01)  # 0.6 units each
        self.assertEqual(mouse.moved[0], 6)

    def test_reset_releases_held_button(self):
        engine, mouse = make_engine()
        engine.frame(3, 0, 0, now=0.0)
        engine.frame(3, 5.0, 0, now=0.01)
        engine.reset()
        self.assertFalse(mouse.pressed)


def touch_frame(decoder, *touches, fingers=None):
    """Feeds one frame of (slot, tracking_id, x, y) touches; returns the frame."""
    result = None
    for slot, tracking_id, x, y in touches:
        decoder.feed(drag.EV_ABS, drag.ABS_MT_SLOT, slot)
        if tracking_id is not None:
            decoder.feed(drag.EV_ABS, drag.ABS_MT_TRACKING_ID, tracking_id)
        if x is not None:
            decoder.feed(drag.EV_ABS, drag.ABS_MT_POSITION_X, x)
        if y is not None:
            decoder.feed(drag.EV_ABS, drag.ABS_MT_POSITION_Y, y)
    if fingers is not None:
        for code, count in drag.FINGER_TOOLS.items():
            decoder.feed(drag.EV_KEY, code, int(count == fingers))
    result = decoder.feed(drag.EV_SYN, drag.SYN_REPORT, 0)
    return result


class FrameDecoderTest(unittest.TestCase):
    def test_mean_motion_of_persistent_fingers(self):
        decoder = drag.FrameDecoder()
        touch_frame(decoder, (0, 10, 100, 100), (1, 11, 200, 100), (2, 12, 300, 100),
                    fingers=3)
        frame = touch_frame(decoder, (0, None, 110, None), (1, None, 210, None),
                            (2, None, 310, 106))
        self.assertEqual(frame[:3], (3, 10.0, 2.0))
        self.assertEqual(frame.touches, {10: (110, 100), 11: (210, 100), 12: (310, 106)})

    def test_lifting_a_finger_does_not_jump(self):
        decoder = drag.FrameDecoder()
        touch_frame(decoder, (0, 10, 100, 100), (1, 11, 500, 500), fingers=2)
        frame = touch_frame(decoder, (1, -1, None, None), fingers=1)
        self.assertEqual(frame[:3], (1, 0.0, 0.0))
        frame = touch_frame(decoder, (0, None, 103, None))
        self.assertEqual(frame[:3], (1, 3.0, 0.0))
        self.assertEqual(frame.touches, {10: (103, 100)})

    def test_new_finger_in_reused_slot_does_not_jump(self):
        decoder = drag.FrameDecoder()
        touch_frame(decoder, (0, 10, 100, 100), fingers=1)
        touch_frame(decoder, (0, -1, None, None), fingers=0)
        frame = touch_frame(decoder, (0, 20, 900, 900), fingers=1)
        self.assertEqual(frame[:3], (1, 0.0, 0.0))

    def test_dropped_events_are_skipped(self):
        decoder = drag.FrameDecoder()
        touch_frame(decoder, (0, 10, 100, 100), fingers=1)
        decoder.feed(drag.EV_SYN, drag.SYN_DROPPED, 0)
        self.assertIsNone(decoder.feed(drag.EV_ABS, drag.ABS_MT_POSITION_X, 999))
        self.assertTrue(decoder.dropped)


def hand(scale, thumb=(50, 60), fingers=((40, 20), (50, 18), (60, 20))):
    """Thumb and three fingers, scaled around their centroid; positions in mm."""
    points = [thumb, *fingers]
    cx = sum(p[0] for p in points) / 4
    cy = sum(p[1] for p in points) / 4
    return {tid: (cx + (x - cx) * scale, cy + (y - cy) * scale)
            for tid, (x, y) in enumerate(points)}


class PinchTrackerTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.tracker = drag.PinchTracker(self.lines.append)

    def run_gesture(self, scales, fingers=4):
        for scale in scales:
            self.tracker.frame(fingers, hand(scale))

    def ratios(self):
        return [round(float(line.split()[1]), 2) for line in self.lines
                if line.startswith("update")]

    def test_pinch_in_streams_ratio(self):
        self.run_gesture([1.0, 0.95, 0.85, 0.7, 0.5])
        self.tracker.frame(0, {})
        self.assertEqual(self.lines[0], "begin")
        self.assertEqual(self.ratios(), [0.85, 0.7, 0.5])
        self.assertEqual(self.lines[-1], "end")

    def test_spread_streams_ratio(self):
        self.run_gesture([1.0, 1.2, 1.6])
        self.assertEqual(self.ratios(), [1.2, 1.6])

    def test_small_jitter_does_not_begin(self):
        self.run_gesture([1.0, 1.03, 0.97, 1.05])
        self.tracker.frame(0, {})
        self.assertEqual(self.lines, [])

    def test_four_finger_swipe_is_not_a_pinch(self):
        for step in range(20):
            scale = 1.0 + step * 0.02  # fingers drift apart a little while swiping
            self.tracker.frame(4, {tid: (x + step * 3, y)
                                   for tid, (x, y) in hand(scale).items()})
        self.assertEqual(self.lines, [])

    def test_three_fingers_never_pinch(self):
        self.run_gesture([1.0, 0.4], fingers=3)
        self.assertEqual(self.lines, [])

    def test_finger_change_mid_pinch_does_not_jump(self):
        self.run_gesture([1.0, 0.8])
        fewer = dict(list(hand(0.7).items())[:3])  # one touch stops being tracked
        self.tracker.frame(4, fewer)
        self.tracker.frame(4, dict(list(hand(0.6).items())[:3]))
        ratios = self.ratios()
        self.assertEqual(ratios[0], 0.8)
        self.assertAlmostEqual(ratios[-1], 0.8 * 0.6 / 0.7, places=2)

    def test_baseline_waits_for_last_finger(self):
        self.tracker.frame(4, dict(list(hand(3.0).items())[:3]))
        self.run_gesture([1.0, 0.95])
        self.assertEqual(self.lines, [])

    def test_next_gesture_starts_fresh(self):
        self.run_gesture([1.0, 0.5])
        self.tracker.frame(0, {})
        self.lines.clear()
        self.run_gesture([1.0, 1.5])
        self.assertEqual(self.lines, ["begin", "update 1.5000"])


class EdgeSwipeDetectorTest(unittest.TestCase):
    RIGHT_EDGE = 120.0

    def setUp(self):
        self.lines = []
        self.detector = drag.EdgeSwipeDetector(self.lines.append, self.RIGHT_EDGE)

    def swipe(self, start_x, dx, dy=0.0, fingers=2, steps=6, ids=(1, 2)):
        for i in range(steps + 1):
            x, y = start_x + dx * i / steps, 40 + dy * i / steps
            self.detector.frame(fingers, {ids[0]: (x, y), ids[1]: (x, y + 15)})
        self.detector.frame(0, {})

    def test_swipe_in_from_right_edge(self):
        self.swipe(start_x=116, dx=-30)
        self.assertEqual(self.lines, ["edge right"])

    def test_swipe_left_from_middle_is_ignored(self):
        self.swipe(start_x=70, dx=-30)
        self.assertEqual(self.lines, [])

    def test_swipe_right(self):
        self.swipe(start_x=40, dx=30)
        self.assertEqual(self.lines, ["swipe right"])

    def test_vertical_scroll_near_edge_is_ignored(self):
        self.swipe(start_x=116, dx=-14, dy=40)
        self.assertEqual(self.lines, [])

    def test_short_swipe_is_ignored(self):
        self.swipe(start_x=116, dx=-8)
        self.assertEqual(self.lines, [])

    def test_fires_once_per_touch(self):
        self.swipe(start_x=116, dx=-60, steps=20)
        self.assertEqual(self.lines, ["edge right"])

    def test_three_fingers_are_ignored(self):
        self.swipe(start_x=116, dx=-30, fingers=3)
        self.assertEqual(self.lines, [])


class GestureServerTest(unittest.TestCase):
    def test_broadcasts_lines_and_drops_closed_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(pathlib.Path(tmp) / "gestures.sock")
            server = drag.GestureServer(path)
            try:
                a, b = (socket.socket(socket.AF_UNIX) for _ in range(2))
                a.connect(path)
                b.connect(path)
                ready, _, _ = select.select(server.fds(), [], [], 1)
                server.handle(ready)
                ready, _, _ = select.select(server.fds(), [], [], 0.1)
                server.handle(ready)
                self.assertEqual(len(server.clients), 2)

                server("begin")
                self.assertEqual(a.recv(100), b"begin\n")
                self.assertEqual(b.recv(100), b"begin\n")

                b.close()
                ready, _, _ = select.select(server.fds(), [], [], 1)
                server.handle(ready)
                self.assertEqual(len(server.clients), 1)
                server("update 0.5000")
                self.assertEqual(a.recv(100), b"update 0.5000\n")
                a.close()
            finally:
                server.close()


class IoctlNumbersTest(unittest.TestCase):
    """Request numbers checked against linux/input.h and linux/uinput.h."""

    def test_known_values(self):
        self.assertEqual(drag.EVIOCGABS(drag.ABS_MT_SLOT), 0x8018456F)
        self.assertEqual(drag.EVIOCGNAME(256), 0x81004506)
        self.assertEqual(drag.UI_SET_EVBIT, 0x40045564)
        self.assertEqual(drag.UI_DEV_SETUP, 0x405C5503)
        self.assertEqual(drag.UI_DEV_CREATE, 0x5501)
        self.assertEqual(drag.EVENT.size, 24)


if __name__ == "__main__":
    unittest.main()
