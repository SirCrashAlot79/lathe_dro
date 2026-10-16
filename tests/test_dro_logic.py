import pytest

from lathe_dro_pro import (
    load_tool_touch_positions,
    compound_rest_angle,
    bolt_circle_coordinates,
    boring_hole_diameter,
    coordinate_midpoint,
    feed_rates_for,
    parse_serial_packet,
    recommend_spindle_step,
    read_serial_packets,
    request_system_poweroff,
    round_to_precision,
    save_tool_touch_positions,
    shoulder_distance,
    spindle_rpm_for_surface_speed,
    thread_setting_for,
    tool_offset_for,
    tool_corrected_x_count,
)


def test_parse_serial_packet_valid_line():
    assert parse_serial_packet("X:123,Z:456,RPM:720") == (123, 456, 720)


def test_parse_serial_packet_empty_line():
    assert parse_serial_packet("") == (0, 0, 0)


@pytest.mark.parametrize("packet", ["X:no,Z:2,RPM:3", "X:1,Z:2", "bad packet"])
def test_parse_serial_packet_rejects_malformed_lines(packet):
    with pytest.raises(ValueError):
        parse_serial_packet(packet)


def test_read_serial_packets_waits_for_complete_line():
    class FakeConnection:
        def __init__(self):
            self.data = b"X:12,Z:34"

        @property
        def in_waiting(self):
            return len(self.data)

        def read(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data

    connection = FakeConnection()
    pending, packet = read_serial_packets(connection, "")
    assert packet is None

    connection.data = b",RPM:56\n"
    pending, packet = read_serial_packets(connection, pending)
    assert pending == ""
    assert packet == (12, 34, 56)


def test_round_to_precision_uses_0005_inch_steps():
    assert round_to_precision(1.23456, metric_mode=False) == 1.2345


def test_round_to_precision_uses_mm_resolution():
    assert round_to_precision(12.34567, metric_mode=True) == 12.346


def test_round_to_precision_accepts_custom_inch_resolution():
    assert round_to_precision(1.23456, metric_mode=False, resolution=0.001) == 1.235


def test_round_to_precision_rejects_nonpositive_resolution():
    with pytest.raises(ValueError):
        round_to_precision(1.0, metric_mode=False, resolution=0)


def test_compound_rest_angle_is_half_taper_angle():
    assert compound_rest_angle(2.0, 1.0, 10.0) == pytest.approx(2.8624052261)


def test_compound_rest_angle_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        compound_rest_angle(2.0, 1.0, 0.0)


@pytest.mark.parametrize(
    "tpi, expected",
    [
        (4, {"tpi": 4, "stud_gear": 40, "tumbler": "A", "selector_column": 1, "longitudinal_feed_in_per_rev": 0.0853}),
        (5.75, {"tpi": 5.75, "stud_gear": 40, "tumbler": "A", "selector_column": 5, "longitudinal_feed_in_per_rev": 0.0594}),
        (11, {"tpi": 11, "stud_gear": 20, "tumbler": "A", "selector_column": 4, "longitudinal_feed_in_per_rev": 0.0310}),
        (224, {"tpi": 224, "stud_gear": 20, "tumbler": "E", "selector_column": 8, "longitudinal_feed_in_per_rev": 0.0015}),
    ],
)
def test_thread_setting_for_chart_pitches(tpi, expected):
    assert thread_setting_for(tpi) == expected


def test_thread_setting_for_returns_none_for_unlisted_pitch():
    assert thread_setting_for(13.5) is None


def test_thread_setting_for_rejects_invalid_tpi():
    with pytest.raises(ValueError):
        thread_setting_for(0)


def test_feed_rates_include_longitudinal_cross_and_per_minute():
    assert feed_rates_for(11, 600) == pytest.approx({
        "longitudinal_per_rev": 0.0310,
        "cross_per_rev": 0.0310 / 3,
        "longitudinal_per_min": 18.6,
        "cross_per_min": 6.2,
    })


def test_feed_rates_convert_chart_values_to_metric():
    rates = feed_rates_for(11, 600, metric=True)
    assert rates["longitudinal_per_rev"] == pytest.approx(0.0310 * 25.4)
    assert rates["longitudinal_per_min"] == pytest.approx(18.6 * 25.4)


def test_spindle_rpm_for_surface_speed_uses_diameter_units():
    assert spindle_rpm_for_surface_speed(2, 100) == pytest.approx(190.9859317)
    assert spindle_rpm_for_surface_speed(50.8, 100, metric=True) == pytest.approx(190.9859317)


def test_spindle_rpm_for_surface_speed_rejects_zero_diameter():
    with pytest.raises(ValueError):
        spindle_rpm_for_surface_speed(0, 100)


@pytest.mark.parametrize(
    "target, drive, speed_range, expected",
    [
        (500, "BELT DRIVE", "LOW RANGE", {"step": 2, "rpm": 410, "spindle": "middle", "at_maximum": False}),
        (150, "BACK GEAR", "LOW RANGE", {"step": 3, "rpm": 135, "spindle": "smallest", "at_maximum": True}),
        (1000, "BELT DRIVE", "HIGH RANGE", {"step": 2, "rpm": 780, "spindle": "middle", "at_maximum": False}),
        (200, "BACK GEAR", "HIGH RANGE", {"step": 2, "rpm": 155, "spindle": "middle", "at_maximum": False}),
        (1365, "BELT DRIVE", "HIGH RANGE", {"step": 3, "rpm": 1365, "spindle": "smallest", "at_maximum": True}),
    ],
)
def test_spindle_step_recommendation_uses_supplied_ranges(target, drive, speed_range, expected):
    assert recommend_spindle_step(target, drive, speed_range) == expected


def test_spindle_step_recommendation_handles_target_below_range():
    assert recommend_spindle_step(200, "BELT DRIVE", "LOW RANGE") is None


def test_spindle_step_recommendation_rejects_invalid_target():
    with pytest.raises(ValueError):
        recommend_spindle_step(0, "BELT DRIVE", "LOW RANGE")


def test_coordinate_helpers_compute_midpoint_and_shoulder_distance():
    assert coordinate_midpoint(2.0, 8.0) == 5.0
    assert shoulder_distance(8.0, 2.0) == 6.0


def test_boring_diameter_adds_twice_radial_x_travel():
    assert boring_hole_diameter(0.5, 1000, 1000 + 2540) == pytest.approx(0.7)


def test_boring_diameter_can_reverse_x_direction_and_convert_metric():
    assert boring_hole_diameter(10, 1000, 1000 - 1000, increasing_direction=-1, metric=True) == pytest.approx(10 + 2.0)


def test_boring_diameter_rejects_invalid_scale_calibration():
    with pytest.raises(ValueError):
        boring_hole_diameter(0.5, 0, 10, pulses_per_inch=0)


def test_boring_x_reference_survives_calibrated_tool_change():
    positions = {1: (1000, 0), 2: (1500, 0)}
    start = tool_corrected_x_count(2000, 1, positions)
    current = tool_corrected_x_count(2000 + 500 + 2540, 2, positions)
    assert current - start == 2540
    assert boring_hole_diameter(0.5, start, current) == pytest.approx(0.7)


def test_poweroff_requests_systemctl_without_prompt(monkeypatch):
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr("lathe_dro_pro.subprocess.run", fake_run)

    assert request_system_poweroff() == (True, "")
    assert calls[0][0] == ["sudo", "-n", "/usr/bin/systemctl", "poweroff"]


def test_poweroff_reports_missing_authorization(monkeypatch):
    class Result:
        returncode = 1
        stdout = ""
        stderr = "a password is required"

    monkeypatch.setattr("lathe_dro_pro.subprocess.run", lambda *args, **kwargs: Result())

    assert request_system_poweroff() == (False, "a password is required")


def test_tool_corrected_x_requires_tool_offset():
    assert tool_corrected_x_count(2000, 2, {1: (1000, 0)}) is None


def test_bolt_circle_coordinates_evenly_spaces_four_holes():
    coordinates = bolt_circle_coordinates(100, 4)
    expected = [(50, 0), (0, 50), (-50, 0), (0, -50)]
    for actual_point, expected_point in zip(coordinates, expected):
        assert actual_point[0] == pytest.approx(expected_point[0])
        assert actual_point[1] == pytest.approx(expected_point[1])


def test_tool_offset_is_relative_to_t1_master():
    positions = {1: (1000, 2000), 2: (1040, 1970)}
    assert tool_offset_for(1, positions) == (0, 0)
    assert tool_offset_for(2, positions) == (40, -30)


def test_tool_offset_requires_master_and_tool_touch_off():
    assert tool_offset_for(2, {2: (1040, 1970)}) is None
    assert tool_offset_for(3, {1: (1000, 2000)}) is None


def test_tool_touch_positions_persist(tmp_path):
    path = tmp_path / "tool_offsets.json"
    positions = {1: (1000, 2000), 2: (1040, 1970)}

    save_tool_touch_positions(path, positions)

    assert load_tool_touch_positions(path) == positions
