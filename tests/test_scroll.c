/* Tests for the scroll shim. Built and run by tests/test_scroll.py. */

#define TRACKPAD_LIKE_MAC_TEST
#include "../src/scroll/trackpad-like-mac-scroll.c"

#include <assert.h>
#include <unistd.h>

static int failures;

#define CHECK_NEAR(actual, expected, tolerance)                                  \
	do {                                                                     \
		double a_ = (actual), e_ = (expected);                           \
		if (fabs(a_ - e_) > (tolerance)) {                               \
			fprintf(stderr, "%s:%d: %s = %.4f, expected %.4f\n",     \
				__FILE__, __LINE__, #actual, a_, e_);           \
			failures++;                                              \
		}                                                                \
	} while (0)

/* A fake libinput event: the shim only passes the pointer back to these. */
struct libinput_event_pointer {
	int type;
	uint64_t time;
	double value[2];
};

static double fake_get_scroll_value(struct libinput_event_pointer *e, int axis)
{
	return e->value[axis];
}

static struct libinput_event *fake_get_base_event(struct libinput_event_pointer *e)
{
	return (struct libinput_event *)e;
}

static int fake_get_type(struct libinput_event *e)
{
	return ((struct libinput_event_pointer *)e)->type;
}

static uint64_t fake_get_time_usec(struct libinput_event_pointer *e)
{
	return e->time;
}

static void reset(void)
{
	memset(axes, 0, sizeof(axes));
	real_get_scroll_value = fake_get_scroll_value;
	get_base_event = fake_get_base_event;
	get_type = fake_get_type;
	get_time_usec = fake_get_time_usec;
	px_per_mm = 5.6;
	slow_ratio = 1.0;
	fast_ratio = 2.5;
	/* Tests run well within one config check interval of this. */
	config_checked = 1;
}

/* Scrolls at a steady finger speed; returns content mm per finger mm. */
static double ratio_at_speed(double mm_per_second)
{
	double finger_mm = 0, scaled = 0;
	for (int i = 1; i <= 20; i++) {
		struct libinput_event_pointer e = {
			LIBINPUT_EVENT_POINTER_SCROLL_FINGER, i * 7000,
			{mm_per_second * FRAME_SECONDS * LIBINPUT_UNITS_PER_MM, 0}};
		finger_mm += e.value[0] / LIBINPUT_UNITS_PER_MM;
		scaled += libinput_event_pointer_get_scroll_value(&e, 0);
	}
	return scaled / px_per_mm / finger_mm;
}

static void test_slow_scroll_follows_finger(void)
{
	reset();
	CHECK_NEAR(ratio_at_speed(20), 1.0, 0.01);
}

static void test_fast_scroll_speeds_up(void)
{
	reset();
	CHECK_NEAR(ratio_at_speed(400), 2.5, 0.05);
	reset();
	double middle = ratio_at_speed((SLOW_SPEED + FAST_SPEED) / 2);
	CHECK_NEAR(middle, 1.75, 0.05);
}

static void test_stop_event_stays_zero(void)
{
	reset();
	struct libinput_event_pointer e = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 7000, {0, 0}};
	assert(libinput_event_pointer_get_scroll_value(&e, 0) == 0.0);
}

static void test_same_event_gets_same_answer(void)
{
	reset();
	struct libinput_event_pointer a = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 7000, {3, 0}};
	struct libinput_event_pointer b = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 14000, {3, 0}};
	libinput_event_pointer_get_scroll_value(&a, 0);
	double first = libinput_event_pointer_get_scroll_value(&b, 0);
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&b, 0), first, 1e-12);
}

static void test_wheel_passes_through(void)
{
	reset();
	struct libinput_event_pointer e = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER - 1, 7000, {15, 0}};
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 15, 0);
}

static void test_unconfigured_passes_through(void)
{
	reset();
	px_per_mm = 0;
	struct libinput_event_pointer e = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 7000, {4, 0}};
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 4, 0);
}

static void test_axes_are_independent(void)
{
	reset();
	struct libinput_event_pointer e = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 7000, {2, -2}};
	double v = libinput_event_pointer_get_scroll_value(&e, 0);
	double h = libinput_event_pointer_get_scroll_value(&e, 1);
	CHECK_NEAR(h, -v, 1e-12);
}

static void test_strip_preload(void)
{
	char out[256];
	strip_preload("/usr/lib/trackpad-like-mac/libtrackpad-like-mac-scroll.so", out, sizeof(out));
	assert(strcmp(out, "") == 0);
	strip_preload("/a.so:/x/libtrackpad-like-mac-scroll.so /b.so", out, sizeof(out));
	assert(strcmp(out, "/a.so:/b.so") == 0);
}

static void test_parse_config(void)
{
	reset();
	px_per_mm = 0;
	parse_config("px_per_mm=6.25 slow=0.9 fast=3");
	CHECK_NEAR(px_per_mm, 6.25, 0);
	CHECK_NEAR(slow_ratio, 0.9, 0);
	CHECK_NEAR(fast_ratio, 3, 0);
	parse_config(NULL);
}

static void test_config_file_is_loaded_and_followed(void)
{
	reset();
	char dir[] = "/tmp/trackpad-like-mac-test-XXXXXX";
	assert(mkdtemp(dir));
	snprintf(config_path, sizeof(config_path), "%s/scroll.conf", dir);
	struct libinput_event_pointer e = {LIBINPUT_EVENT_POINTER_SCROLL_FINGER, 0, {4, 0}};

	/* No file: scrolling is untouched. */
	e.time = 2 * CONFIG_CHECK_INTERVAL;
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 4, 0);

	FILE *file = fopen(config_path, "w");
	fputs("px_per_mm=10.5 slow=2 fast=2\n", file);
	fclose(file);
	/* Not re-checked within the interval... */
	e.time += CONFIG_CHECK_INTERVAL / 2;
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 4, 0);
	/* ...but picked up after it: 2 content mm per finger mm at 1 px/unit. */
	e.time += CONFIG_CHECK_INTERVAL;
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 8, 1e-9);

	remove(config_path);
	e.time += 2 * CONFIG_CHECK_INTERVAL;
	CHECK_NEAR(libinput_event_pointer_get_scroll_value(&e, 0), 4, 0);
	rmdir(dir);
	config_path[0] = '\0';
}

int main(void)
{
	test_slow_scroll_follows_finger();
	test_fast_scroll_speeds_up();
	test_stop_event_stays_zero();
	test_same_event_gets_same_answer();
	test_wheel_passes_through();
	test_unconfigured_passes_through();
	test_axes_are_independent();
	test_strip_preload();
	test_parse_config();
	test_config_file_is_loaded_and_followed();
	if (failures)
		return 1;
	puts("scroll shim: all tests passed");
	return 0;
}
