// SPDX-License-Identifier: GPL-3.0-or-later
// macOS-style touchpad gestures for GNOME Shell:
//
// - Moves GNOME's built-in gestures (workspace switching, overview, app grid
//   paging) from three to four fingers, leaving three fingers free for
//   dragging, as on macOS with three-finger drag enabled. GNOME Shell
//   hardcodes three fingers in swipeTracker.js, so each gesture's stage
//   handler is re-connected through a wrapper that swaps the finger count the
//   gesture sees: four becomes three (handled) and three becomes four
//   (ignored).
// - Adds the thumb-and-three-fingers pinches: pinching in opens the app grid
//   (Launchpad), spreading out shows the desktop, and the opposite pinch
//   undoes either. Animations follow the fingers and settle or snap back on
//   release. libinput often treats the thumb as resting and reports a
//   pinch-in as a three-finger swipe, so the trackpad-like-mac daemon
//   tracks pinches on the raw touches and streams them over GESTURE_SOCKET.
// - A two-finger swipe in from the right edge of the touchpad opens the
//   notification list (Notification Center); swiping right closes it.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

// Created by the root daemon in a root-owned directory, so what it sends can
// be trusted. Pinch lines: "begin", "update <spread ratio>", "end";
// two-finger swipes: "edge right", "swipe right".
const GESTURE_SOCKET = '/run/trackpad-like-mac/gestures.sock';
const RECONNECT_SECONDS = 2;

// Spread ratios at which a pinch animation is complete, and the progress past
// which lifting the fingers finishes it instead of snapping back.
const FULL_IN_RATIO = 0.55;
const FULL_OUT_RATIO = 1.8;
const COMMIT_PROGRESS = 0.35;
const SETTLE_MS = 250;

// Overview states (ControlsState in overviewControls.js).
const OVERVIEW_HIDDEN = 0;
const APP_GRID = 2;

Gio._promisify(Gio.SocketClient.prototype, 'connect_async');
Gio._promisify(Gio.DataInputStream.prototype, 'read_line_async');

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function swapFingers(event) {
    if (event.type() !== Clutter.EventType.TOUCHPAD_SWIPE)
        return event;

    const fingers = event.get_touchpad_gesture_finger_count();
    const swapped = {3: 4, 4: 3}[fingers];
    if (swapped === undefined)
        return event;

    return new Proxy(event, {
        get(target, prop) {
            if (prop === 'get_touchpad_gesture_finger_count')
                return () => swapped;
            const value = target[prop];
            return typeof value === 'function' ? value.bind(target) : value;
        },
    });
}

function touchpadGestures() {
    const controls = Main.overview._overview?._controls;
    return [
        Main.overview._swipeTracker,
        Main.wm._workspaceAnimation?._swipeTracker,
        controls?._workspacesDisplay?._swipeTracker,
        controls?._appDisplay?._swipeTracker,
    ].map(tracker => tracker?._touchpadGesture).filter(Boolean);
}

/** Reads gesture lines from the daemon, reconnecting whenever it restarts. */
class GestureStream {
    constructor(onLine) {
        this._onLine = onLine;
        this._cancellable = new Gio.Cancellable();
        this._reconnectId = 0;
        this._connect();
    }

    destroy() {
        this._cancellable.cancel();
        if (this._reconnectId)
            GLib.source_remove(this._reconnectId);
    }

    async _connect() {
        let connection = null;
        try {
            connection = await new Gio.SocketClient().connect_async(
                new Gio.UnixSocketAddress({path: GESTURE_SOCKET}), this._cancellable);
            const input = new Gio.DataInputStream({
                base_stream: connection.get_input_stream(),
            });
            const decoder = new TextDecoder();
            for (;;) {
                const [line] = await input.read_line_async(
                    GLib.PRIORITY_DEFAULT, this._cancellable);
                if (line === null)
                    break;
                this._onLine(decoder.decode(line));
            }
        } catch {
            // Not running yet, restarted, or cancelled; handled below.
        }
        connection?.close(null);
        if (this._cancellable.is_cancelled())
            return;

        this._onLine('end');
        this._reconnectId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT,
            RECONNECT_SECONDS, () => {
                this._reconnectId = 0;
                this._connect();
                return GLib.SOURCE_REMOVE;
            });
    }
}

/** Drives the overview (window picker / app grid) like its own swipe gesture. */
class OverviewPinch {
    constructor(target) {
        this._target = target;
        // Main.overview's gesture callbacks expect its SwipeTracker; this
        // stands in for it.
        this._tracker = {
            confirmSwipe: (distance, points, progress, cancelProgress) => {
                this._start = progress;
                this._cancel = cancelProgress;
            },
        };
        Main.overview._gestureBegin(this._tracker);
    }

    update(progress) {
        Main.overview._gestureUpdate(this._tracker,
            this._start + (this._target - this._start) * progress);
    }

    end(commit) {
        Main.overview._gestureEnd(this._tracker, SETTLE_MS,
            commit ? this._target : this._cancel);
    }
}

/**
 * Slides windows off screen as the fingers spread (show desktop), or back on
 * screen as they pinch (restore). Windows end up minimized while hidden.
 */
class DesktopPinch {
    // onDone(windows) runs when the gesture completes: with the hidden
    // windows after a spread, with null after a restore.
    constructor(windows, restoring, onDone) {
        this._restoring = restoring;
        this._onDone = onDone;
        this._windows = windows.map(window => ({
            window,
            actor: window.get_compositor_private(),
            ...offscreenOffset(window),
        }));
        if (restoring) {
            for (const {window, actor, dx, dy} of this._windows) {
                actor.set({translation_x: dx, translation_y: dy, opacity: 0});
                Main.wm.skipNextEffect(actor);
                window.unminimize();
            }
        }
    }

    update(progress) {
        this._place(this._restoring ? 1 - progress : progress);
    }

    end(commit) {
        const hidden = this._restoring !== commit;
        for (const {window, actor, dx, dy} of this._windows) {
            actor.ease({
                translation_x: hidden ? dx : 0,
                translation_y: hidden ? dy : 0,
                opacity: hidden ? 0 : 255,
                duration: SETTLE_MS,
                mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
                onStopped: () => {
                    if (!hidden)
                        return;
                    Main.wm.skipNextEffect(actor);
                    window.minimize();
                    actor.set({translation_x: 0, translation_y: 0, opacity: 255});
                },
            });
        }
        if (this._restoring && commit)
            this._windows.at(-1)?.window.activate(global.get_current_time());
        if (commit)
            this._onDone(hidden ? this._windows.map(w => w.window) : null);
    }

    // out: 0 = in place, 1 = fully off screen.
    _place(out) {
        for (const {actor, dx, dy} of this._windows) {
            actor.set({
                translation_x: dx * out,
                translation_y: dy * out,
                opacity: Math.round(255 * (1 - out * out)),
            });
        }
    }
}

/** How far to move a window, away from its monitor's center, to leave it. */
function offscreenOffset(window) {
    const rect = window.get_buffer_rect();
    const monitor = global.display.get_monitor_geometry(window.get_monitor());
    let vx = rect.x + rect.width / 2 - (monitor.x + monitor.width / 2);
    let vy = rect.y + rect.height / 2 - (monitor.y + monitor.height / 2);
    const length = Math.hypot(vx, vy);
    [vx, vy] = length < 1 ? [0, -1] : [vx / length, vy / length];

    const margin = 32;
    const distances = [];
    if (vx > 0)
        distances.push((monitor.x + monitor.width - rect.x + margin) / vx);
    else if (vx < 0)
        distances.push((rect.x + rect.width - monitor.x + margin) / -vx);
    if (vy > 0)
        distances.push((monitor.y + monitor.height - rect.y + margin) / vy);
    else if (vy < 0)
        distances.push((rect.y + rect.height - monitor.y + margin) / -vy);
    const distance = Math.min(...distances);
    return {dx: vx * distance, dy: vy * distance};
}

class PinchGestures {
    constructor() {
        this._hidden = null;  // {workspace, windows} while the desktop is shown
        this._pinch = null;
        this._direction = null;
        this._progress = 0;
        // libinput's own pinches of four or more fingers are swallowed so
        // apps don't also zoom; the daemon's stream drives the animations.
        global.stage.connectObject('captured-event::touchpad',
            this._swallowPinch.bind(this), this);
        this._stream = new GestureStream(this._onLine.bind(this));
    }

    destroy() {
        this._stream.destroy();
        global.stage.disconnectObject(this);
        this._finish();
    }

    _swallowPinch(actor, event) {
        return event.type() === Clutter.EventType.TOUCHPAD_PINCH &&
            event.get_touchpad_gesture_finger_count() >= 4
            ? Clutter.EVENT_STOP
            : Clutter.EVENT_PROPAGATE;
    }

    _onLine(line) {
        const [kind, value] = line.split(' ');
        if (kind === 'begin') {
            this._finish();
        } else if (kind === 'update') {
            const ratio = Number(value);
            if (!this._direction) {
                // The first movement decides what this gesture does.
                this._direction = ratio < 1 ? 'in' : 'out';
                this._progress = 0;
                this._pinch = this._startPinch(this._direction);
            }
            this._progress = this._direction === 'in'
                ? clamp((1 - ratio) / (1 - FULL_IN_RATIO), 0, 1)
                : clamp((ratio - 1) / (FULL_OUT_RATIO - 1), 0, 1);
            this._pinch?.update(this._progress);
        } else if (kind === 'end') {
            this._finish();
        } else if (kind === 'edge' || kind === 'swipe') {
            this._onSwipe(kind);
        }
    }

    _onSwipe(kind) {
        const isOpen = Main.panel.statusArea.dateMenu?.menu.isOpen;
        // While the menu is open the action mode is POPUP, so only opening
        // is limited to the normal desktop and the overview.
        const allowedModes = Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW;
        if (kind === 'edge' && !isOpen && (Main.actionMode & allowedModes) !== 0)
            Main.panel.toggleCalendar();
        else if (kind === 'swipe' && isOpen)
            Main.panel.closeCalendar();
    }

    _finish() {
        this._pinch?.end(this._progress >= COMMIT_PROGRESS);
        this._pinch = null;
        this._direction = null;
        this._progress = 0;
    }

    _startPinch(direction) {
        const allowedModes = Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW;
        if ((Main.actionMode & allowedModes) === 0)
            return null;

        const overviewState = Main.overview.visible
            ? Main.overview._overview.controls._stateAdjustment.value
            : OVERVIEW_HIDDEN;

        if (direction === 'in') {
            const hidden = this._hiddenWindows();
            if (hidden.length > 0 && !Main.overview.visible)
                return new DesktopPinch(hidden, true, this._onDesktopDone.bind(this));
            return overviewState < APP_GRID ? new OverviewPinch(APP_GRID) : null;
        }

        if (Main.overview.visible)
            return new OverviewPinch(OVERVIEW_HIDDEN);
        const workspace = global.workspace_manager.get_active_workspace();
        const windows = workspace.list_windows().filter(w =>
            !w.minimized && !w.skip_taskbar && w.can_minimize() &&
            w.get_window_type() === Meta.WindowType.NORMAL &&
            w.get_compositor_private());
        if (windows.length === 0)
            return null;
        return new DesktopPinch(global.display.sort_windows_by_stacking(windows),
            false, this._onDesktopDone.bind(this));
    }

    _onDesktopDone(hiddenWindows) {
        this._hidden = hiddenWindows && {
            workspace: global.workspace_manager.get_active_workspace(),
            windows: hiddenWindows,
        };
    }

    // Windows the last spread hid that are still there and still minimized;
    // empty if the user switched workspace or brought them back otherwise.
    _hiddenWindows() {
        if (this._hidden?.workspace !== global.workspace_manager.get_active_workspace())
            return [];
        const alive = new Set(global.get_window_actors().map(a => a.meta_window));
        return this._hidden.windows.filter(w => alive.has(w) && w.minimized);
    }
}

export default class TrackpadLikeMacExtension extends Extension {
    enable() {
        this._gestures = touchpadGestures();
        for (const gesture of this._gestures) {
            global.stage.disconnectObject(gesture);
            global.stage.connectObject('captured-event::touchpad',
                (actor, event) => gesture._handleEvent(actor, swapFingers(event)),
                gesture);
        }
        this._pinch = new PinchGestures();
    }

    disable() {
        for (const gesture of this._gestures ?? []) {
            global.stage.disconnectObject(gesture);
            global.stage.connectObject('captured-event::touchpad',
                gesture._handleEvent.bind(gesture), gesture);
        }
        this._gestures = null;
        this._pinch?.destroy();
        this._pinch = null;
    }
}
