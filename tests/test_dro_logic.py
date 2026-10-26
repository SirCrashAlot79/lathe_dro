import pytest

import lathe_dro_pro as dro
from lathe_dro_pro import (
    load_tool_touch_positions,
    compound_rest_angle,
    bolt_circle_coordinates,
    boring_hole_diameter,
    coordinate_midpoint,
    parse_serial_packet,
    counts_for_machine,
    recommend_spindle_step,
    read_serial_packets,
    request_system_poweroff,
    round_to_precision,
    save_tool_touch_positions,
    load_scale_calibration,
    mill_half_origin,
    mill_preset_origin,
    save_scale_calibration,
    shoulder_distance,
    scale_compensation_for_travel,
    spindle_rpm_for_surface_speed,
    thread_setting_for,
    tool_offset_for,
    tool_corrected_x_count,
    tool_x_offset_to_counts,
    tool_position_with_manual_x_offset,
    wrap_text,
)


def test_parse_serial_packet_valid_line():
    assert parse_serial_packet("LX:123,LZ:456,MX:789,MY:321,MZ:654,RPM:720") == (
        123, 456, 789, 321, 654, 720
    )


def test_parse_serial_packet_supports_legacy_xyz_packet():
    assert parse_serial_packet("X:123,Y:789,Z:456,RPM:720") == (
        123, 456, 123, 789, 456, 720
    )


def test_parse_serial_packet_supports_legacy_lathe_packet():
    assert parse_serial_packet("X:123,Z:456,RPM:720") == (
        123, 456, 123, 0, 456, 720
    )


def test_counts_for_machine_selects_independent_scale_counts():
    lathe_counts = (123, 456)
    mill_counts = (789, 321, 654)
    assert counts_for_machine("lathe", lathe_counts, mill_counts) == (123, 0, 456)
    assert counts_for_machine("mill", lathe_counts, mill_counts) == mill_counts


def test_parse_serial_packet_empty_line():
    assert parse_serial_packet("") == (0, 0, 0, 0, 0, 0)


@pytest.mark.parametrize("packet", ["X:no,Z:2,RPM:3", "X:1,Z:2", "bad packet"])
def test_parse_serial_packet_rejects_malformed_lines(packet):
    with pytest.raises(ValueError):
        parse_serial_packet(packet)


def test_read_serial_packets_waits_for_complete_line():
    class FakeConnection:
        def __init__(self):
            self.data = b"LX:12,LZ:34,MX:56,MY:78,MZ:90"

        @property
        def in_waiting(self):
            return len(self.data)

        def read(self, size):
            data, self.data = self.data[:size], self.data[size:]
            return data

    connection = FakeConnection()
    pending, packet = read_serial_packets(connection, "")
    assert packet is None

    connection.data = b",RPM:78\n"
    pending, packet = read_serial_packets(connection, pending)
    assert pending == ""
    assert packet == (12, 34, 56, 78, 90, 78)


def test_round_to_precision_uses_0005_inch_steps():
    assert round_to_precision(1.23456, metric_mode=False) == 1.2345


def test_round_to_precision_uses_mm_resolution():
    assert round_to_precision(12.34567, metric_mode=True) == 12.346


def test_round_to_precision_accepts_custom_inch_resolution():
    assert round_to_precision(1.23456, metric_mode=False, resolution=0.001) == 1.235


def test_round_to_precision_rejects_nonpositive_resolution():
    with pytest.raises(ValueError):
        round_to_precision(1.0, metric_mode=False, resolution=0)


def test_scale_compensation_for_travel_calibrates_nominal_counts():
    assert scale_compensation_for_travel(1.0, 25400) == pytest.approx(1.0)
    assert scale_compensation_for_travel(25.4, -25400, metric=True) == pytest.approx(1.0)


def test_mill_preset_origin_sets_requested_inch_and_metric_coordinates():
    assert mill_preset_origin(50000, 1.0, 1.0) == 24600
    assert mill_preset_origin(50000, 25.4, 1.0, metric=True) == 24600
    assert mill_preset_origin(50000, -1.0, 1.0, direction=-1) == 24600


def test_mill_half_origin_halves_current_position_without_losing_counts():
    assert mill_half_origin(50000, 24600) == 37300
    assert mill_half_origin(50000, 50000) == 50000


def test_mill_preset_origin_rejects_bad_axis_direction_and_calibration():
    with pytest.raises(ValueError):
        mill_preset_origin(1000, 1.0, 1.0, direction=0)
    with pytest.raises(ValueError):
        mill_preset_origin(1000, 1.0, 0)


def test_mill_scale_calibration_saves_separately_from_lathe(tmp_path, monkeypatch):
    lathe_factors = {"x": 1.002, "y": 1.0, "z": 0.998}
    mill_factors = {"x": 1.01, "y": 1.0, "z": 0.99}
    monkeypatch.setattr(dro, "scale_calibration_factors", lathe_factors)
    monkeypatch.setattr(dro, "mill_scale_calibration_factors", mill_factors)

    path = tmp_path / "mill_scale_calibration.json"
    dro.set_mill_scale_compensation("Y", 1.005, path=path)

    assert dro.mill_scale_calibration_factors == {"x": 1.01, "y": 1.005, "z": 0.99}
    assert dro.scale_calibration_factors == lathe_factors
    assert load_scale_calibration(path) == {"x": 1.01, "y": 1.005, "z": 0.99}


@pytest.mark.parametrize(
    "distance, count_delta, metric",
    [(0, 1000, False), (1, 0, False), (-1, 1000, False)],
)
def test_scale_compensation_for_travel_rejects_invalid_measurements(
    distance, count_delta, metric
):
    with pytest.raises(ValueError):
        scale_compensation_for_travel(distance, count_delta, metric=metric)


def test_scale_calibration_persists_and_ignores_invalid_factors(tmp_path):
    path = tmp_path / "scale_calibration.json"
    save_scale_calibration(path, {"x": 1.002, "y": 1.001, "z": 0.998})
    assert load_scale_calibration(path) == {"x": 1.002, "y": 1.001, "z": 0.998}

    path.write_text('{"x": -1, "z": "invalid"}', encoding="utf-8")
    assert load_scale_calibration(path) == {"x": 1.0, "y": 1.0, "z": 1.0}


def test_compound_rest_angle_is_half_taper_angle():
    assert compound_rest_angle(2.0, 1.0, 10.0) == pytest.approx(2.8624052261)


def test_compound_rest_angle_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        compound_rest_angle(2.0, 1.0, 0.0)


@pytest.mark.parametrize(
    "tpi, expected",
    [
        (4, {"tpi": 4, "stud_gear": 40, "tumbler": "A", "selector_column": 1}),
        (6.75, {"tpi": 6.75, "stud_gear": 40, "tumbler": "A", "selector_column": 8}),
        (15, {"tpi": 15, "stud_gear": 40, "tumbler": "B", "selector_column": 10}),
        (40, {"tpi": 40, "stud_gear": 40, "tumbler": "D", "selector_column": 3}),
        (224, {"tpi": 224, "stud_gear": 40, "tumbler": "F", "selector_column": 9}),
        (480, {"tpi": 480, "stud_gear": 40, "tumbler": "G", "selector_column": 10}),
    ],
)
def test_thread_setting_for_chart_pitches(tpi, expected):
    assert thread_setting_for(tpi) == expected


def test_thread_chart_has_seven_rows_and_ten_selector_positions():
    chart = (
        (4, 4.5, 5, 5.5, 5.75, 6, 6.5, 6.75, 7, 7.5),
        (8, 9, 10, 11, 11.5, 12, 13, 13.5, 14, 15),
        (16, 18, 20, 22, 23, 24, 26, 27, 28, 30),
        (32, 36, 40, 44, 46, 48, 52, 54, 56, 60),
        (64, 72, 80, 88, 92, 96, 104, 108, 112, 120),
        (128, 144, 160, 176, 184, 192, 208, 216, 224, 240),
        (256, 288, 320, 352, 368, 384, 416, 432, 448, 480),
    )

    for row_index, pitches in enumerate(chart):
        for column, tpi in enumerate(pitches, start=1):
            assert thread_setting_for(tpi) == {
                "tpi": tpi,
                "stud_gear": 40,
                "tumbler": chr(ord("A") + row_index),
                "selector_column": column,
            }


def test_thread_setting_for_returns_none_for_unlisted_pitch():
    assert thread_setting_for(13.25) is None


def test_thread_setting_for_rejects_invalid_tpi():
    with pytest.raises(ValueError):
        thread_setting_for(0)


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


def test_wrap_text_keeps_lines_inside_available_width():
    import pygame
    pygame.font.init()
    font = pygame.font.SysFont("sans", 24)
    lines = wrap_text("A long setup message must stay clear of the keypad buttons.", font, 180)
    assert len(lines) > 1
    assert all(font.size(line)[0] <= 180 for line in lines)


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


def test_tool_x_offset_to_counts_respects_units_diameter_mode_and_sign():
    assert tool_x_offset_to_counts(0.5, diameter_mode=True) == 6350
    assert tool_x_offset_to_counts(-25.4, metric=True) == -25400
    assert tool_x_offset_to_counts(1.0, linear_error_comp=1.01) == 25149


@pytest.mark.parametrize("factor", [0, -1])
def test_tool_x_offset_to_counts_rejects_invalid_compensation(factor):
    with pytest.raises(ValueError):
        tool_x_offset_to_counts(1.0, linear_error_comp=factor)


def test_manual_tool_x_offset_is_relative_to_t1_and_preserves_z():
    positions = {1: (1000, 2000), 2: (1100, 2050)}
    assert tool_position_with_manual_x_offset(2, -75, positions) == (925, 2050)
    assert tool_position_with_manual_x_offset(3, 125, positions) == (1125, 2000)


def test_manual_tool_x_offset_requires_t1_and_nonmaster_tool():
    with pytest.raises(ValueError):
        tool_position_with_manual_x_offset(2, 10, {})
    with pytest.raises(ValueError):
        tool_position_with_manual_x_offset(1, 10, {1: (100, 200)})


def test_tool_touch_positions_persist(tmp_path):
    path = tmp_path / "tool_offsets.json"
    positions = {1: (1000, 2000), 2: (1040, 1970)}

    save_tool_touch_positions(path, positions)

    assert load_tool_touch_positions(path) == positions
