/* SPDX-License-Identifier: GPL-3.0-or-later */
/*
 * macOS-like two-finger scrolling for GNOME Shell.
 *
 * Loaded with LD_PRELOAD into gnome-shell only, it wraps libinput's
 * libinput_event_pointer_get_scroll_value() and rescales touchpad (finger)
 * scrolling: slow scrolls move the content as far as the fingers moved and
 * fast ones speed up, as on macOS. libinput scrolls a fixed ~10.5 logical
 * pixels per finger millimetre whatever the screen, which on dense screens
 * runs well ahead of the fingers. Wheel and other scroll sources pass through.
 *
 * Configured per user by ~/.config/trackpad-like-mac/scroll.conf, written by
 * `trackpad-like-mac setup` and re-read when it changes:
 *   px_per_mm=5.6 slow=1.0 fast=2.5
 * px_per_mm is the screen's logical pixels per physical millimetre; slow and
 * fast are how far the content moves per finger millimetre at slow and fast
 * finger speeds. Without the file, scrolling is left untouched.
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

struct libinput_event;
struct libinput_event_pointer;

/* From libinput.h; part of libinput's stable ABI. */
#define LIBINPUT_EVENT_POINTER_SCROLL_FINGER 405

/* libinput's finger scroll units per finger millimetre (measured; libinput
 * normalizes touchpads by their physical resolution). */
#define LIBINPUT_UNITS_PER_MM 10.5
/* Finger speeds (mm/s) at which the slow and fast ratios apply; in between,
 * the ratio is interpolated. */
#define SLOW_SPEED 40.0
#define FAST_SPEED 250.0
/* Libinput reports finger scrolling about every 7 ms; a longer pause (µs)
 * starts a new scroll. */
#define FRAME_SECONDS 0.007
#define NEW_SCROLL_GAP 50000

/* How often (µs) to check whether the config file changed. */
#define CONFIG_CHECK_INTERVAL 1000000

#define PRELOAD_NAME "trackpad-like-mac-scroll"
#define CONFIG_FILE "/trackpad-like-mac/scroll.conf"

static double px_per_mm;
static double slow_ratio = 1.0;
static double fast_ratio = 2.5;

static char config_path[4096];
static struct timespec config_mtime;
static uint64_t config_checked;

static double (*real_get_scroll_value)(struct libinput_event_pointer *, int);
static struct libinput_event *(*get_base_event)(struct libinput_event_pointer *);
static int (*get_type)(struct libinput_event *);
static uint64_t (*get_time_usec)(struct libinput_event_pointer *);

struct axis_state {
	uint64_t last_time;
	double speed;  /* smoothed finger speed, mm/s */
	/* The last answer, since mutter may ask more than once per event. */
	struct libinput_event_pointer *event;
	uint64_t event_time;
	double raw, scaled;
};

/* libinput's input thread is the only caller, so no locking is needed. */
static struct axis_state axes[2];

static double clamp(double value, double min, double max)
{
	return value < min ? min : value > max ? max : value;
}

static double scale_scroll(struct axis_state *state, double raw, uint64_t time)
{
	if (raw == 0.0) {
		/* A scroll stop: must stay exactly zero. */
		state->last_time = 0;
		state->speed = 0.0;
		return 0.0;
	}

	int continuing = state->last_time && time > state->last_time &&
			 time - state->last_time < NEW_SCROLL_GAP;
	double seconds = continuing ? (time - state->last_time) / 1e6 : FRAME_SECONDS;
	double speed = fabs(raw) / LIBINPUT_UNITS_PER_MM / seconds;
	state->speed = continuing ? 0.5 * state->speed + 0.5 * speed : speed;
	state->last_time = time;

	double t = clamp((state->speed - SLOW_SPEED) / (FAST_SPEED - SLOW_SPEED), 0.0, 1.0);
	double ratio = slow_ratio + (fast_ratio - slow_ratio) * t;
	return raw * ratio * px_per_mm / LIBINPUT_UNITS_PER_MM;
}

static void parse_config(const char *config)
{
	char key[32];
	double value;
	int consumed;

	px_per_mm = 0.0;
	slow_ratio = 1.0;
	fast_ratio = 2.5;
	while (config && sscanf(config, " %31[^=]=%lf%n", key, &value, &consumed) == 2) {
		if (strcmp(key, "px_per_mm") == 0)
			px_per_mm = value;
		else if (strcmp(key, "slow") == 0)
			slow_ratio = value;
		else if (strcmp(key, "fast") == 0)
			fast_ratio = value;
		config += consumed;
	}
}

/* Re-reads the config file if it changed; a missing file turns scaling off. */
static void reload_config(void)
{
	struct stat st;
	if (!config_path[0] || stat(config_path, &st) != 0) {
		px_per_mm = 0.0;
		config_mtime = (struct timespec){0};
		return;
	}
	if (st.st_mtim.tv_sec == config_mtime.tv_sec &&
	    st.st_mtim.tv_nsec == config_mtime.tv_nsec)
		return;
	config_mtime = st.st_mtim;

	char text[256] = "";
	FILE *file = fopen(config_path, "r");
	if (file) {
		size_t length = fread(text, 1, sizeof(text) - 1, file);
		text[length] = '\0';
		fclose(file);
	}
	parse_config(text);
}

double libinput_event_pointer_get_scroll_value(struct libinput_event_pointer *event,
					       int axis)
{
	if (!real_get_scroll_value)
		return 0.0;

	double raw = real_get_scroll_value(event, axis);
	if (!get_base_event || !get_type || !get_time_usec || axis < 0 || axis > 1)
		return raw;

	uint64_t time = get_time_usec(event);
	if (!config_checked || time - config_checked >= CONFIG_CHECK_INTERVAL) {
		config_checked = time;
		reload_config();
	}
	if (px_per_mm <= 0.0 ||
	    get_type(get_base_event(event)) != LIBINPUT_EVENT_POINTER_SCROLL_FINGER)
		return raw;

	struct axis_state *state = &axes[axis];
	if (state->event == event && state->event_time == time && state->raw == raw)
		return state->scaled;

	state->event = event;
	state->event_time = time;
	state->raw = raw;
	state->scaled = scale_scroll(state, raw, time);
	return state->scaled;
}

/* Copies value without the entries naming this library, so programs started
 * from GNOME Shell don't inherit it. */
static void strip_preload(const char *value, char *out, size_t size)
{
	char *copy = strdup(value);
	char *saveptr = NULL;
	size_t used = 0;

	out[0] = '\0';
	if (!copy)
		return;
	for (char *entry = strtok_r(copy, ": ", &saveptr); entry;
	     entry = strtok_r(NULL, ": ", &saveptr)) {
		if (strstr(entry, PRELOAD_NAME))
			continue;
		int written = snprintf(out + used, size - used, "%s%s",
				       used ? ":" : "", entry);
		if (written < 0 || (size_t)written >= size - used)
			break;
		used += written;
	}
	free(copy);
}

#ifndef TRACKPAD_LIKE_MAC_TEST
__attribute__((constructor))
static void init(void)
{
	const char *preload = getenv("LD_PRELOAD");
	if (preload) {
		char rest[4096];
		strip_preload(preload, rest, sizeof(rest));
		if (rest[0])
			setenv("LD_PRELOAD", rest, 1);
		else
			unsetenv("LD_PRELOAD");
	}

	real_get_scroll_value = dlvsym(RTLD_NEXT, "libinput_event_pointer_get_scroll_value",
				       "LIBINPUT_1.19");
	if (!real_get_scroll_value)
		real_get_scroll_value = dlsym(RTLD_NEXT, "libinput_event_pointer_get_scroll_value");
	get_base_event = dlsym(RTLD_NEXT, "libinput_event_pointer_get_base_event");
	get_type = dlsym(RTLD_NEXT, "libinput_event_get_type");
	get_time_usec = dlsym(RTLD_NEXT, "libinput_event_pointer_get_time_usec");

	const char *config_home = getenv("XDG_CONFIG_HOME");
	const char *home = getenv("HOME");
	if (config_home && config_home[0] == '/')
		snprintf(config_path, sizeof(config_path), "%s%s", config_home, CONFIG_FILE);
	else if (home)
		snprintf(config_path, sizeof(config_path), "%s/.config%s", home, CONFIG_FILE);
}
#endif
