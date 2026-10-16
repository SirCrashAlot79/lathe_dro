import argparse
import json
import math
from pathlib import Path
import sys
import pygame
import serial
from serial.tools import list_ports

# --- CONFIGURATION INITIALIZATION ---
PULSES_PER_INCH = 25400.0
DEMO_MODE = False
TOOL_OFFSETS_FILE = Path(__file__).with_name("tool_offsets.json")
THREADING_CHART = (
    (40, "A", (4, 4.5, 5, 5.5, 5.75, 6, 6.5, 7), (0.0853, 0.0758, 0.0683, 0.0621, 0.0594, 0.0569, 0.0525, 0.0488)),
    (20, "A", (8, 9, 10, 11, 11.5, 12, 13, 14), (0.0427, 0.0379, 0.0341, 0.0310, 0.0297, 0.0284, 0.0263, 0.0244)),
    (20, "B", (16, 18, 20, 22, 23, 24, 26, 28), (0.0213, 0.0190, 0.0171, 0.0155, 0.0148, 0.0142, 0.0131, 0.0122)),
    (20, "C", (32, 36, 40, 44, 46, 48, 52, 56), (0.0106, 0.0095, 0.0085, 0.0078, 0.0074, 0.0071, 0.0066, 0.0061)),
    (20, "D", (64, 72, 80, 88, 92, 96, 104, 112), (0.0053, 0.0047, 0.0043, 0.0039, 0.0036, 0.0034, 0.0033, 0.0030)),
    (20, "E", (128, 144, 160, 176, 184, 192, 208, 224), (0.0027, 0.0024, 0.0021, 0.0019, 0.0018, 0.0016, 0.0016, 0.0015)),
)
CROSS_FEED_RATIO = 1 / 3
HSS_SURFACE_SPEED_SFM = {
    "Mild steel": 80,
    "Aluminum": 200,
    "Stainless steel": 50,
    "Cast iron": 60,
}
SPINDLE_SPEED_STEPS = {
    ("BELT DRIVE", "LOW RANGE"): (240, 410, 715),
    ("BACK GEAR", "LOW RANGE"): (50, 78, 135),
    ("BELT DRIVE", "HIGH RANGE"): (460, 780, 1365),
    ("BACK GEAR", "HIGH RANGE"): (90, 155, 265),
}


def parse_serial_packet(line):
    """Parse one firmware packet in X:<count>,Z:<count>,RPM:<rpm> format."""
    if not line.strip():
        return 0, 0, 0

    values = {}
    for field in line.strip().split(","):
        key, value = field.split(":", 1)
        values[key.strip().upper()] = int(value.strip())

    try:
        return values["X"], values["Z"], values["RPM"]
    except KeyError as error:
        raise ValueError(f"Missing {error.args[0]} field in serial packet") from error


def find_pico_port():
    for port in list_ports.comports():
        description = (port.description or "").lower()
        if port.vid == 0x2E8A or "pico" in description:
            return port.device
    return None


def read_serial_packets(connection, pending_data):
    if connection is None or not connection.in_waiting:
        return pending_data, None

    pending_data += connection.read(connection.in_waiting).decode("ascii", errors="ignore")
    latest_packet = None
    while "\n" in pending_data:
        line, pending_data = pending_data.split("\n", 1)
        if not line.strip():
            continue
        try:
            latest_packet = parse_serial_packet(line)
        except (ValueError, KeyError):
            continue
    if len(pending_data) > 1024:
        pending_data = pending_data[-1024:]
    return pending_data, latest_packet


def open_pico_connection(port, baudrate):
    selected_port = port or find_pico_port()
    if selected_port is None:
        return None, "Pico not found; use --port or --demo"
    try:
        return serial.Serial(selected_port, baudrate=baudrate, timeout=0), f"Connected: {selected_port}"
    except serial.SerialException as error:
        return None, f"Serial connection failed: {error}"


def load_tool_touch_positions(path=TOOL_OFFSETS_FILE):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    positions = {}
    for tool_id, coordinates in data.items():
        try:
            tool_id = int(tool_id)
            x_position = int(coordinates["x"])
            z_position = int(coordinates["z"])
        except (KeyError, TypeError, ValueError):
            continue
        if 1 <= tool_id <= 9:
            positions[tool_id] = (x_position, z_position)
    return positions


def save_tool_touch_positions(path, positions):
    data = {
        str(tool_id): {"x": x_position, "z": z_position}
        for tool_id, (x_position, z_position) in positions.items()
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def tool_offset_for(tool_id, positions):
    reference = positions.get(1)
    tool_position = positions.get(tool_id)
    if reference is None or tool_position is None:
        return None
    return tool_position[0] - reference[0], tool_position[1] - reference[1]


def tool_corrected_x_count(x_pulses, tool_id, positions):
    offset = tool_offset_for(tool_id, positions)
    if offset is None:
        return None
    return x_pulses - offset[0]

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description="Lathe digital readout")
    argument_parser.add_argument("--port", help="Pico USB serial port, for example /dev/ttyACM0")
    argument_parser.add_argument("--baud", type=int, default=115200)
    argument_parser.add_argument("--demo", action="store_true", help="Use simulated readings")
    display_group = argument_parser.add_mutually_exclusive_group()
    display_group.add_argument("--fullscreen", dest="fullscreen", action="store_true")
    display_group.add_argument("--windowed", dest="fullscreen", action="store_false")
    argument_parser.set_defaults(fullscreen=sys.platform.startswith("linux"))
    arguments = argument_parser.parse_args()

    pygame.init()
    if arguments.fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption("South Bend 10k Pro Toolroom DRO")
    width, height = screen.get_size()
    font_large = pygame.font.SysFont("courier", int(height * 0.13), bold=True)
    font_medium = pygame.font.SysFont("sans", int(height * 0.05), bold=True)
    font_small = pygame.font.SysFont("sans", int(height * 0.032))
    font_logo = pygame.font.SysFont("serif", int(height * 0.13), bold=True)
else:
    screen = None
    width, height = 1280, 720

# --- THEME STYLING ---
BLACK = (11, 15, 17)
GREY = (20, 27, 29)
MED_GREY = (31, 40, 42)
LIGHT_GREY = (82, 96, 98)
CYAN = (95, 190, 202)
YELLOW = (235, 174, 72)
WHITE = (225, 230, 226)
GREEN = (137, 194, 132)
MAGENTA = (78, 155, 166)
RED = (208, 78, 68)


def draw_industrial_background(target, target_width, target_height):
    target.fill(BLACK)
    for y in range(28, target_height - 12, 32):
        pygame.draw.line(target, (15, 20, 22), (0, y), (target_width, y), 1)
    pygame.draw.rect(target, (25, 33, 35), (0, 0, target_width, 12))
    pygame.draw.line(target, YELLOW, (0, 12), (target_width, 12), 2)
    pygame.draw.line(target, LIGHT_GREY, (0, target_height - 10), (target_width, target_height - 10), 2)
    pygame.draw.rect(target, (7, 10, 12), (0, target_height - 8, target_width, 8))
    pygame.draw.line(target, (48, 60, 62), (14, 20), (14, target_height - 20), 2)

# --- APP STATES ---
STATE_MAIN_DRO = 0
STATE_SETUP_MENU = 1
STATE_TOOL_SETUP = 2
STATE_BOOT = 3
STATE_TAPER = 4
STATE_THREAD = 5
STATE_SPEED = 6
STATE_COORD = 7
STATE_BORING = 8
BOOT_DURATION_MS = 2500
current_state = STATE_BOOT

# --- SYSTEM & CALIBRATION CALCULATION REGISTERS ---
x_pulses, z_pulses, rpm = 0, 0, 0
x_abs_zero, z_abs_zero = 0, 0
x_inc_zero, z_inc_zero = 0, 0
tool_touch_positions = load_tool_touch_positions()
is_diameter_mode = True
is_metric = False
is_abs_mode = True
current_tool_id = 1
operation_mode = "TURNING"
boring_initial_diameter = ""
boring_start_x_counts = None
boring_start_tool_id = None
boring_start_tool_offset = None
boring_direction = 1
boring_metric = False
boring_status = ""

# User Adjustable Parameters via Setup Panel
resolution_tier = 0.0005     # Toggles: 0.0001, 0.0005, 0.0010
x_linear_error_comp = 1.0000 # Scaling factor to calibrate physical deviations
z_linear_error_comp = 1.0000
backlash_x = 0.0000          # For mechanical backlash storage

def round_to_precision(value, metric_mode, resolution=0.0005):
    """Dynamically steps values according to active resolution constraints."""
    if metric_mode:
        return round(value, 3)
    if resolution <= 0:
        raise ValueError("resolution must be greater than zero")
    steps_per_inch = 1.0 / resolution
    return round(value * steps_per_inch) / steps_per_inch


def compound_rest_angle(large_diameter, small_diameter, taper_length):
    dimensions = (large_diameter, small_diameter, taper_length)
    if not all(math.isfinite(value) for value in dimensions):
        raise ValueError("dimensions must be finite numbers")
    if large_diameter < 0 or small_diameter < 0 or taper_length <= 0:
        raise ValueError("diameters must be non-negative and length must be positive")
    return math.degrees(math.atan(abs(large_diameter - small_diameter) / (2 * taper_length)))


def thread_setting_for(tpi):
    try:
        requested_tpi = float(tpi)
    except (TypeError, ValueError) as error:
        raise ValueError("TPI must be a positive number") from error
    if not math.isfinite(requested_tpi) or requested_tpi <= 0:
        raise ValueError("TPI must be a positive number")

    for stud_gear, tumbler, pitches, feeds in THREADING_CHART:
        for column, chart_tpi in enumerate(pitches, start=1):
            if math.isclose(requested_tpi, chart_tpi, rel_tol=0, abs_tol=1e-9):
                return {
                    "tpi": chart_tpi,
                    "stud_gear": stud_gear,
                    "tumbler": tumbler,
                    "selector_column": column,
                    "longitudinal_feed_in_per_rev": feeds[column - 1],
                }
    return None


def feed_rates_for(tpi, rpm, metric=False):
    setting = thread_setting_for(tpi)
    if setting is None:
        return None
    try:
        rpm = float(rpm)
    except (TypeError, ValueError) as error:
        raise ValueError("RPM must be a non-negative number") from error
    if not math.isfinite(rpm) or rpm < 0:
        raise ValueError("RPM must be a non-negative number")

    unit_scale = 25.4 if metric else 1.0
    longitudinal = setting["longitudinal_feed_in_per_rev"] * unit_scale
    cross = longitudinal * CROSS_FEED_RATIO
    return {
        "longitudinal_per_rev": longitudinal,
        "cross_per_rev": cross,
        "longitudinal_per_min": longitudinal * rpm,
        "cross_per_min": cross * rpm,
    }


def spindle_rpm_for_surface_speed(diameter, surface_speed_sfm, metric=False):
    if not math.isfinite(diameter) or not math.isfinite(surface_speed_sfm):
        raise ValueError("diameter and surface speed must be finite numbers")
    if diameter <= 0 or surface_speed_sfm <= 0:
        raise ValueError("diameter and surface speed must be positive")
    diameter_inches = diameter / 25.4 if metric else diameter
    return 12 * surface_speed_sfm / (math.pi * diameter_inches)


def recommend_spindle_step(target_rpm, drive_mode, speed_range):
    try:
        target_rpm = float(target_rpm)
    except (TypeError, ValueError) as error:
        raise ValueError("target RPM must be positive") from error
    if not math.isfinite(target_rpm) or target_rpm <= 0:
        raise ValueError("target RPM must be positive")
    try:
        available_speeds = SPINDLE_SPEED_STEPS[(drive_mode, speed_range)]
    except KeyError as error:
        raise ValueError("unknown spindle drive or range") from error

    safe_steps = [
        (step_number, rpm)
        for step_number, rpm in enumerate(available_speeds, start=1)
        if rpm <= target_rpm
    ]
    if not safe_steps:
        return None
    step_number, rpm = safe_steps[-1]
    return {
        "step": step_number,
        "rpm": rpm,
        "spindle": ("largest", "middle", "smallest")[step_number - 1],
        "at_maximum": step_number == len(available_speeds),
    }


def coordinate_midpoint(first, second):
    if not math.isfinite(first) or not math.isfinite(second):
        raise ValueError("coordinates must be finite numbers")
    return (first + second) / 2


def shoulder_distance(first, second):
    if not math.isfinite(first) or not math.isfinite(second):
        raise ValueError("coordinates must be finite numbers")
    return abs(second - first)


def boring_hole_diameter(initial_diameter, initial_x_counts, current_x_counts,
                         increasing_direction=1, metric=False,
                         pulses_per_inch=PULSES_PER_INCH, linear_error_comp=1.0):
    values = (initial_diameter, initial_x_counts, current_x_counts, pulses_per_inch, linear_error_comp)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("boring inputs must be finite numbers")
    if initial_diameter < 0 or pulses_per_inch <= 0 or linear_error_comp <= 0:
        raise ValueError("diameter must be non-negative and calibration values positive")
    if increasing_direction not in (-1, 1):
        raise ValueError("increasing direction must be 1 or -1")

    radial_travel_inches = (current_x_counts - initial_x_counts) / pulses_per_inch
    radial_travel_inches *= linear_error_comp * increasing_direction
    diameter_increase = radial_travel_inches * 2
    if metric:
        diameter_increase *= 25.4
    return initial_diameter + diameter_increase


def bolt_circle_coordinates(pitch_circle_diameter, hole_count, start_angle_degrees=0):
    values = (pitch_circle_diameter, start_angle_degrees)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("bolt-circle dimensions must be finite numbers")
    if pitch_circle_diameter <= 0 or not isinstance(hole_count, int) or hole_count < 2:
        raise ValueError("PCD must be positive and hole count must be an integer of at least 2")

    radius = pitch_circle_diameter / 2
    return [
        (
            radius * math.cos(math.radians(start_angle_degrees + index * 360 / hole_count)),
            radius * math.sin(math.radians(start_angle_degrees + index * 360 / hole_count)),
        )
        for index in range(hole_count)
    ]

# --- UI INTERACTION BOUNDARIES ---
panel_x = int(width * 0.75)
btn_w = int(width * 0.11)
btn_h = int(height * 0.12)
col1_x = panel_x + 10
col2_x = panel_x + btn_w + 20

main_buttons = {
    "TURNING": pygame.Rect(40, 20, 230, 54),
    "BORING": pygame.Rect(282, 20, 230, 54),
    "DIA":     pygame.Rect(col1_x, int(height*0.02), btn_w, btn_h),
    "INCH/MM": pygame.Rect(col2_x, int(height*0.02), btn_w, btn_h),
    "ZERO_X":  pygame.Rect(col1_x, int(height*0.16), btn_w, btn_h),
    "ABS/INC": pygame.Rect(col2_x, int(height*0.16), btn_w, btn_h),
    "ZERO_Z":  pygame.Rect(col1_x, int(height*0.30), btn_w, btn_h),
    "TOOL_LIB":pygame.Rect(col2_x, int(height*0.30), btn_w, btn_h),
    "TOOL_SETUP": pygame.Rect(col1_x, int(height*0.44), btn_w, btn_h),
    "FEED":    pygame.Rect(col2_x, int(height*0.44), btn_w, btn_h),
    "TAPER":   pygame.Rect(col1_x, int(height*0.58), btn_w, btn_h),
    "SPEED":   pygame.Rect(col2_x, int(height*0.58), btn_w, btn_h),
    "COORD":   pygame.Rect(col1_x, int(height*0.72), btn_w, btn_h),
    "SETUP":   pygame.Rect(col2_x, int(height*0.72), btn_w, btn_h)
}

boring_input_rect = pygame.Rect(50, 165, 500, 70)
boring_buttons = {
    "TURNING": pygame.Rect(40, 20, 230, 54),
    "CAPTURE": pygame.Rect(50, 275, 500, 75),
    "DIRECTION": pygame.Rect(50, 370, 500, 60),
}
boring_readout_width = int(width * 0.115)
boring_readout_gap = int(width * 0.008)
boring_readout_start = width - 20 - 3 * boring_readout_width - 2 * boring_readout_gap
boring_readout_rects = {
    name: pygame.Rect(boring_readout_start + index * (boring_readout_width + boring_readout_gap), 20, boring_readout_width, 56)
    for index, name in enumerate(("X", "Z", "RPM"))
}
boring_zero_buttons = {
    "X": pygame.Rect(boring_readout_rects["X"].x, 84, boring_readout_width, 38),
    "Z": pygame.Rect(boring_readout_rects["Z"].x, 84, boring_readout_width, 38),
}
boring_tool_button = pygame.Rect(boring_readout_rects["RPM"].x, 84, boring_readout_width, 38)

setup_buttons = {
    "RES_TOGGLE": pygame.Rect(50, 150, 300, 60),
    "COMP_X_UP":  pygame.Rect(50, 300, 140, 60),
    "COMP_X_DN":  pygame.Rect(210, 300, 140, 60),
    "COMP_Z_UP":  pygame.Rect(50, 450, 140, 60),
    "COMP_Z_DN":  pygame.Rect(210, 450, 140, 60),
    "BACK_MAIN":  pygame.Rect(width - 350, height - 120, 300, 80)
}

tool_setup_buttons = {
    "PREVIOUS": pygame.Rect(60, 150, 140, 70),
    "NEXT": pygame.Rect(220, 150, 140, 70),
    "CAPTURE": pygame.Rect(60, 390, 300, 80),
    "BACK": pygame.Rect(width - 350, height - 120, 300, 80)
}

taper_values = {"large": "", "small": "", "length": ""}
active_taper_field = "large"
taper_fields = {
    "large": pygame.Rect(50, 150, 500, 70),
    "small": pygame.Rect(50, 265, 500, 70),
    "length": pygame.Rect(50, 380, 500, 70)
}
keypad_keys = ("7", "8", "9", "4", "5", "6", "1", "2", "3", ".", "0", "DEL")
keypad_buttons = {}
keypad_x = int(width * 0.57)
keypad_y = int(height * 0.20)
keypad_w = int(width * 0.10)
keypad_h = int(height * 0.09)
keypad_gap_x = int(width * 0.012)
keypad_gap_y = int(height * 0.018)
for keypad_index, keypad_key in enumerate(keypad_keys):
    keypad_row, keypad_column = divmod(keypad_index, 3)
    keypad_buttons[keypad_key] = pygame.Rect(
        keypad_x + keypad_column * (keypad_w + keypad_gap_x),
        keypad_y + keypad_row * (keypad_h + keypad_gap_y),
        keypad_w,
        keypad_h
    )
taper_buttons = {
    "CLEAR": pygame.Rect(keypad_x, keypad_y + 4 * (keypad_h + keypad_gap_y), 3 * keypad_w + 2 * keypad_gap_x, 55),
    "BACK": pygame.Rect(width - 350, height - 120, 300, 80)
}
thread_input = ""
thread_input_rect = pygame.Rect(50, 170, 500, 80)
thread_buttons = {
    "CLEAR": taper_buttons["CLEAR"],
    "BACK": taper_buttons["BACK"]
}
speed_material_names = tuple(HSS_SURFACE_SPEED_SFM)
speed_material_index = 0
speed_values = {"diameter": "", "sfm": str(HSS_SURFACE_SPEED_SFM[speed_material_names[0]])}
active_speed_field = "diameter"
speed_fields = {
    "diameter": pygame.Rect(50, 170, 500, 70),
    "sfm": pygame.Rect(50, 300, 500, 70)
}
speed_material_button = pygame.Rect(50, 390, 500, 50)
speed_drive_button = pygame.Rect(50, 450, 500, 55)
speed_range_button = pygame.Rect(50, 515, 500, 55)
speed_drive_mode = "BELT DRIVE"
speed_range_mode = "LOW RANGE"
speed_buttons = {
    "CLEAR": taper_buttons["CLEAR"],
    "BACK": taper_buttons["BACK"]
}
coord_mode = "MIDPOINT"
coord_values = {"first": "", "second": "", "pcd": "", "holes": "", "start": "0"}
active_coord_field = "first"
coord_mode_buttons = {
    "MIDPOINT": pygame.Rect(50, 95, 180, 55),
    "DISTANCE": pygame.Rect(245, 95, 180, 55),
    "BOLT CIRCLE": pygame.Rect(440, 95, 210, 55)
}
coord_fields = {
    "first": pygame.Rect(50, 190, 520, 70),
    "second": pygame.Rect(50, 300, 520, 70),
    "pcd": pygame.Rect(50, 190, 160, 70),
    "holes": pygame.Rect(230, 190, 160, 70),
    "start": pygame.Rect(410, 190, 160, 70)
}
coord_buttons = {
    "CLEAR": taper_buttons["CLEAR"],
    "BACK": taper_buttons["BACK"]
}

serial_connection = None
serial_buffer = ""
connection_status = "Disconnected"
if __name__ == "__main__":
    DEMO_MODE = arguments.demo
    if DEMO_MODE:
        connection_status = "DEMO MODE"
    else:
        serial_connection, connection_status = open_pico_connection(arguments.port, arguments.baud)
    running = True
    boot_started_ms = pygame.time.get_ticks()
else:
    running = False
    boot_started_ms = 0

clock = pygame.time.Clock() if running else None
frame_counter = 0

while running:
    frame_counter += 1
    
    # 1. READ INTERACTION TARGETING BASED ON VIEW STATE
    pos = (0, 0)
    clicked = False
    
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
            running = False
        elif event.type == pygame.MOUSEBUTTONDOWN:
            pos = event.pos
            clicked = True

    # 2. RUN SIMULATED HARDWARE FEEDBACK ENGINE
    if DEMO_MODE:
        if frame_counter % 2 == 0:
            x_pulses += int(10 * math.sin(frame_counter / 60.0))
            z_pulses += int(35 * math.cos(frame_counter / 120.0))
        rpm = int(720 + (12 * math.sin(frame_counter / 15.0)))
    elif serial_connection is not None:
        try:
            serial_buffer, packet = read_serial_packets(serial_connection, serial_buffer)
            if packet is not None:
                x_pulses, z_pulses, rpm = packet
        except serial.SerialException:
            connection_status = "Serial connection lost"
            serial_connection.close()
            serial_connection = None

    # 3. EVALUATE WINDOW EXECUTION STATES
    if current_state == STATE_BOOT:
        elapsed_ms = pygame.time.get_ticks() - boot_started_ms
        if elapsed_ms >= BOOT_DURATION_MS:
            current_state = STATE_MAIN_DRO
        else:
            draw_industrial_background(screen, width, height)
            center_x = width // 2
            logo_text = font_logo.render("SOUTH BEND", True, WHITE)
            screen.blit(logo_text, logo_text.get_rect(center=(center_x, int(height * 0.39))))
            pygame.draw.line(screen, YELLOW, (int(width * 0.28), int(height * 0.49)), (int(width * 0.72), int(height * 0.49)), 3)
            subtitle = font_medium.render("LATHE DIGITAL READOUT", True, YELLOW)
            screen.blit(subtitle, subtitle.get_rect(center=(center_x, int(height * 0.57))))

            boot_status = "DEMO STARTING" if DEMO_MODE else "CONNECTING TO PICO"
            status_text = font_small.render(boot_status, True, CYAN)
            screen.blit(status_text, status_text.get_rect(center=(center_x, int(height * 0.68))))

            bar_width = int(width * 0.46)
            bar_height = max(8, int(height * 0.014))
            bar_x = (width - bar_width) // 2
            bar_y = int(height * 0.76)
            pygame.draw.rect(screen, GREY, (bar_x, bar_y, bar_width, bar_height), border_radius=2)
            fill_width = int(bar_width * elapsed_ms / BOOT_DURATION_MS)
            pygame.draw.rect(screen, CYAN, (bar_x, bar_y, fill_width, bar_height), border_radius=2)
    elif current_state == STATE_MAIN_DRO:
        # --- MAIN READOUT DISPLAY SCREEN LOGIC ---
        if clicked:
            if main_buttons["SETUP"].collidepoint(pos):
                current_state = STATE_SETUP_MENU  # SWAP THE SCREEN STATE HERE
            elif main_buttons["TURNING"].collidepoint(pos):
                operation_mode = "TURNING"
            elif main_buttons["BORING"].collidepoint(pos):
                operation_mode = "BORING"
                current_state = STATE_BORING
            elif main_buttons["TOOL_SETUP"].collidepoint(pos):
                current_state = STATE_TOOL_SETUP
            elif main_buttons["TAPER"].collidepoint(pos):
                current_state = STATE_TAPER
            elif main_buttons["FEED"].collidepoint(pos):
                current_state = STATE_THREAD
            elif main_buttons["SPEED"].collidepoint(pos):
                current_state = STATE_SPEED
            elif main_buttons["COORD"].collidepoint(pos):
                current_state = STATE_COORD
            elif main_buttons["DIA"].collidepoint(pos):
                is_diameter_mode = not is_diameter_mode
            elif main_buttons["INCH/MM"].collidepoint(pos):
                is_metric = not is_metric
            elif main_buttons["ABS/INC"].collidepoint(pos):
                is_abs_mode = not is_abs_mode
                if not is_abs_mode:
                    x_inc_zero, z_inc_zero = x_pulses, z_pulses
            elif main_buttons["ZERO_X"].collidepoint(pos):
                if is_abs_mode:
                    offset = tool_offset_for(current_tool_id, tool_touch_positions)
                    x_abs_zero = x_pulses - (offset[0] if offset is not None else 0)
                else:
                    x_inc_zero = x_pulses
            elif main_buttons["ZERO_Z"].collidepoint(pos):
                if is_abs_mode:
                    offset = tool_offset_for(current_tool_id, tool_touch_positions)
                    z_abs_zero = z_pulses - (offset[1] if offset is not None else 0)
                else:
                    z_inc_zero = z_pulses
            elif main_buttons["TOOL_LIB"].collidepoint(pos):
                current_tool_id = 1 if current_tool_id >= 9 else current_tool_id + 1

        # Axis unit processing including Linear Scale Correction parameters
        x_origin = x_abs_zero if is_abs_mode else x_inc_zero
        z_origin = z_abs_zero if is_abs_mode else z_inc_zero
        tool_offset = tool_offset_for(current_tool_id, tool_touch_positions) if is_abs_mode else None
        x_tool_offset, z_tool_offset = tool_offset or (0, 0)
        x_val = ((x_pulses - x_origin - x_tool_offset) / PULSES_PER_INCH) * x_linear_error_comp
        z_val = ((z_pulses - z_origin - z_tool_offset) / PULSES_PER_INCH) * z_linear_error_comp
        
        if is_metric:
            x_val *= 25.4
            z_val *= 25.4
        if is_diameter_mode:
            x_val *= 2.0

        x_display = round_to_precision(x_val, is_metric, resolution_tier)
        z_display = round_to_precision(z_val, is_metric, resolution_tier)
        fmt = "0.3f" if is_metric else "0.4f"

        # DRAW MAIN HUD STAGE
        draw_industrial_background(screen, width, height)
        pygame.draw.line(screen, GREY, (0, int(height*0.33)), (panel_x, int(height*0.33)), 4)
        pygame.draw.line(screen, GREY, (0, int(height*0.66)), (panel_x, int(height*0.66)), 4)
        pygame.draw.line(screen, GREY, (panel_x, 0), (panel_x, height), 4)

        screen.blit(font_medium.render("X", True, WHITE), (40, int(height * 0.165)))
        screen.blit(font_large.render(format(x_display, fmt), True, CYAN), (150, int(height * 0.125)))
        screen.blit(font_medium.render("Z", True, WHITE), (40, int(height * 0.41)))
        screen.blit(font_large.render(format(z_display, fmt), True, WHITE), (150, int(height * 0.37)))
        screen.blit(font_medium.render("SPINDLE", True, WHITE), (40, int(height * 0.74)))
        screen.blit(font_large.render(f"{rpm}", True, GREEN), (320, int(height * 0.70)))
        screen.blit(font_medium.render("RPM", True, GREEN), (width * 0.58, int(height * 0.74)))
        status_color = GREEN if DEMO_MODE or serial_connection is not None else RED
        screen.blit(font_small.render(connection_status, True, status_color), (40, int(height * 0.94)))

        # DRAW SIDEBAR INTERACTIVE TILES
        for btn_name, rect in main_buttons.items():
            b_color = GREY
            t_color = WHITE
            if btn_name == "TURNING" and operation_mode == "TURNING": b_color, t_color = YELLOW, BLACK
            elif btn_name == "BORING" and operation_mode == "BORING": b_color, t_color = YELLOW, BLACK
            elif btn_name == "DIA": b_color, t_color = YELLOW, BLACK
            elif btn_name == "INCH/MM": b_color, t_color = MAGENTA, BLACK
            elif btn_name == "ABS/INC": b_color, t_color = CYAN, BLACK
            elif btn_name in ("SETUP", "TOOL_SETUP"): b_color, t_color = RED, WHITE
            
            pygame.draw.rect(screen, b_color, rect)
            pygame.draw.rect(screen, LIGHT_GREY, rect, 2)
            if btn_name == "DIA":
                label_text = "DIA" if is_diameter_mode else "RAD"
            elif btn_name in ("TURNING", "BORING"):
                label_text = btn_name
            elif btn_name == "INCH/MM":
                label_text = "MM" if is_metric else "INCH"
            elif btn_name == "ABS/INC":
                label_text = "ABS" if is_abs_mode else "INC"
            elif btn_name == "TOOL_SETUP":
                label_text = "TOOL SET"
            else:
                label_text = f"T-{current_tool_id}" if btn_name == "TOOL_LIB" else btn_name
            lbl = font_small.render(label_text, True, t_color)
            screen.blit(lbl, lbl.get_rect(center=rect.center))

    elif current_state == STATE_BORING:
        if clicked:
            if boring_buttons["TURNING"].collidepoint(pos):
                operation_mode = "TURNING"
                current_state = STATE_MAIN_DRO
            elif boring_buttons["CAPTURE"].collidepoint(pos):
                if DEMO_MODE:
                    boring_status = "Live Pico readings required for capture"
                elif not boring_initial_diameter:
                    boring_status = "Enter initial drill diameter first"
                else:
                    boring_start_tool_offset = tool_offset_for(current_tool_id, tool_touch_positions)
                    boring_start_x_counts = x_pulses - (boring_start_tool_offset[0] if boring_start_tool_offset else 0)
                    boring_start_tool_id = current_tool_id
                    boring_metric = is_metric
                    boring_status = "Start X captured; bore diameter is live"
            elif boring_buttons["DIRECTION"].collidepoint(pos):
                boring_direction *= -1
                if boring_start_x_counts is not None:
                    boring_status = "X direction changed; recapture the start position"
                    boring_start_x_counts = None
            elif boring_zero_buttons["X"].collidepoint(pos):
                if is_abs_mode:
                    offset = tool_offset_for(current_tool_id, tool_touch_positions)
                    x_abs_zero = x_pulses - (offset[0] if offset is not None else 0)
                else:
                    x_inc_zero = x_pulses
            elif boring_zero_buttons["Z"].collidepoint(pos):
                if is_abs_mode:
                    offset = tool_offset_for(current_tool_id, tool_touch_positions)
                    z_abs_zero = z_pulses - (offset[1] if offset is not None else 0)
                else:
                    z_inc_zero = z_pulses
            elif boring_tool_button.collidepoint(pos):
                next_tool_id = 1 if current_tool_id >= 9 else current_tool_id + 1
                next_tool_offset = tool_offset_for(next_tool_id, tool_touch_positions)
                if boring_start_x_counts is not None and next_tool_id != boring_start_tool_id:
                    if boring_start_tool_offset is None or next_tool_offset is None:
                        boring_start_x_counts = None
                        boring_start_tool_id = None
                        boring_start_tool_offset = None
                        boring_status = "Tool X offset missing; capture X start again"
                    else:
                        boring_status = f"T-{next_tool_id} selected; saved offset retained bore reference"
                current_tool_id = next_tool_id
            elif boring_input_rect.collidepoint(pos):
                pass
            elif taper_buttons["CLEAR"].collidepoint(pos):
                boring_initial_diameter = ""
                boring_start_x_counts = None
                boring_status = ""
            else:
                for key, rect in keypad_buttons.items():
                    if rect.collidepoint(pos):
                        if key == "DEL":
                            boring_initial_diameter = boring_initial_diameter[:-1]
                        elif key == ".":
                            if "." not in boring_initial_diameter:
                                boring_initial_diameter += "."
                        elif len(boring_initial_diameter) < 12:
                            boring_initial_diameter += key
                        boring_start_x_counts = None
                        break

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("CENTER BORING", True, YELLOW), (300, 35))
        x_origin = x_abs_zero if is_abs_mode else x_inc_zero
        z_origin = z_abs_zero if is_abs_mode else z_inc_zero
        tool_offset = tool_offset_for(current_tool_id, tool_touch_positions) if is_abs_mode else None
        x_tool_offset, z_tool_offset = tool_offset or (0, 0)
        x_reading = ((x_pulses - x_origin - x_tool_offset) / PULSES_PER_INCH) * x_linear_error_comp
        z_reading = ((z_pulses - z_origin - z_tool_offset) / PULSES_PER_INCH) * z_linear_error_comp
        if is_metric:
            x_reading *= 25.4
            z_reading *= 25.4
        if is_diameter_mode:
            x_reading *= 2.0
        unit = "mm" if is_metric else "in"
        readout_values = {"X": f"{x_reading:.4f} {unit}", "Z": f"{z_reading:.4f} {unit}", "RPM": f"{rpm}"}
        for name, rect in boring_readout_rects.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, LIGHT_GREY, rect, 2)
            label = font_small.render(name, True, CYAN if name != "RPM" else GREEN)
            value = font_small.render(readout_values[name], True, WHITE)
            screen.blit(label, (rect.x + 8, rect.y + 3))
            screen.blit(value, (rect.x + 8, rect.y + 29))
        for axis, rect in boring_zero_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, LIGHT_GREY, rect, 2)
            zero_text = font_small.render(f"ZERO {axis}", True, WHITE)
            screen.blit(zero_text, zero_text.get_rect(center=rect.center))
        pygame.draw.rect(screen, YELLOW, boring_tool_button)
        pygame.draw.rect(screen, LIGHT_GREY, boring_tool_button, 2)
        tool_text = font_small.render(f"T-{current_tool_id}", True, BLACK)
        screen.blit(tool_text, tool_text.get_rect(center=boring_tool_button.center))

        screen.blit(font_small.render("INITIAL HOLE DIAMETER (measure actual for best accuracy)", True, CYAN), (50, 125))
        pygame.draw.rect(screen, MED_GREY, boring_input_rect)
        pygame.draw.rect(screen, YELLOW, boring_input_rect, 3)
        input_text = font_medium.render(f"{boring_initial_diameter or 'Enter diameter'} {unit}", True, WHITE)
        screen.blit(input_text, input_text.get_rect(midleft=(boring_input_rect.x + 20, boring_input_rect.centery)))

        for key, rect in keypad_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            key_text = font_medium.render(key, True, WHITE)
            screen.blit(key_text, key_text.get_rect(center=rect.center))

        capture_rect = boring_buttons["CAPTURE"]
        capture_color = MED_GREY if DEMO_MODE else GREEN
        pygame.draw.rect(screen, capture_color, capture_rect)
        pygame.draw.rect(screen, WHITE, capture_rect, 2)
        capture_label = "LIVE PICO REQUIRED" if DEMO_MODE else "SET X START AT INITIAL BORE SIZE"
        capture_text = font_small.render(capture_label, True, WHITE if DEMO_MODE else BLACK)
        screen.blit(capture_text, capture_text.get_rect(center=capture_rect.center))

        direction_rect = boring_buttons["DIRECTION"]
        pygame.draw.rect(screen, MED_GREY, direction_rect)
        pygame.draw.rect(screen, CYAN, direction_rect, 2)
        direction_label = "X+ INCREASES DIAMETER" if boring_direction > 0 else "X- INCREASES DIAMETER"
        direction_text = font_small.render(direction_label, True, WHITE)
        screen.blit(direction_text, direction_text.get_rect(center=direction_rect.center))

        current_tool_offset = tool_offset_for(current_tool_id, tool_touch_positions)
        if boring_initial_diameter and boring_start_x_counts is not None:
            if current_tool_id == boring_start_tool_id:
                current_boring_x_counts = x_pulses - (current_tool_offset[0] if current_tool_offset else 0)
            elif boring_start_tool_offset is not None and current_tool_offset is not None:
                current_boring_x_counts = tool_corrected_x_count(x_pulses, current_tool_id, tool_touch_positions)
            else:
                current_boring_x_counts = None
            if current_boring_x_counts is None:
                bore_text = "TOOL OFFSET REQUIRED; recapture X start"
                bore_color = RED
            else:
                try:
                    current_bore_diameter = boring_hole_diameter(
                        float(boring_initial_diameter),
                        boring_start_x_counts,
                        current_boring_x_counts,
                        increasing_direction=boring_direction,
                        metric=boring_metric,
                        linear_error_comp=x_linear_error_comp,
                    )
                    bore_text = f"EST. BORE DIAMETER: {current_bore_diameter:.4f} {'mm' if boring_metric else 'in'}"
                    bore_color = GREEN
                except ValueError as error:
                    bore_text = str(error)
                    bore_color = RED
        elif boring_initial_diameter:
            bore_text = f"READY TO CAPTURE START: {boring_initial_diameter} {unit}"
            bore_color = WHITE
        else:
            bore_text = "Enter the drilled hole size, then set the X start."
            bore_color = WHITE
        screen.blit(font_medium.render(bore_text, True, bore_color), (50, 475))
        screen.blit(font_small.render("Capture X at the start size; bore outward. Verify the estimate with a bore gauge.", True, WHITE), (50, 545))
        if boring_status:
            screen.blit(font_small.render(boring_status, True, YELLOW), (50, 580))

        turning_rect = boring_buttons["TURNING"]
        pygame.draw.rect(screen, YELLOW, turning_rect)
        pygame.draw.rect(screen, LIGHT_GREY, turning_rect, 2)
        turning_text = font_small.render("TURNING / BACK", True, BLACK)
        screen.blit(turning_text, turning_text.get_rect(center=turning_rect.center))

    elif current_state == STATE_COORD:
        if clicked:
            if coord_buttons["BACK"].collidepoint(pos):
                current_state = STATE_MAIN_DRO
            else:
                for mode_name, rect in coord_mode_buttons.items():
                    if rect.collidepoint(pos):
                        coord_mode = mode_name
                        active_coord_field = "pcd" if coord_mode == "BOLT CIRCLE" else "first"
                        break
                else:
                    field_names = ("pcd", "holes", "start") if coord_mode == "BOLT CIRCLE" else ("first", "second")
                    for field_name in field_names:
                        if coord_fields[field_name].collidepoint(pos):
                            active_coord_field = field_name
                            break
                    else:
                        if coord_buttons["CLEAR"].collidepoint(pos):
                            coord_values[active_coord_field] = ""
                        else:
                            for key, rect in keypad_buttons.items():
                                if rect.collidepoint(pos):
                                    value = coord_values[active_coord_field]
                                    if key == "DEL":
                                        coord_values[active_coord_field] = value[:-1]
                                    elif key == ".":
                                        if active_coord_field != "holes" and "." not in value:
                                            coord_values[active_coord_field] = value + "."
                                    elif len(value) < 12:
                                        coord_values[active_coord_field] = value + key
                                    break

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("DRO COORDINATE TOOLS", True, YELLOW), (50, 30))
        for mode_name, rect in coord_mode_buttons.items():
            selected = mode_name == coord_mode
            pygame.draw.rect(screen, CYAN if selected else MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            text = font_small.render(mode_name, True, BLACK if selected else WHITE)
            screen.blit(text, text.get_rect(center=rect.center))

        unit = "mm" if is_metric else "in"
        result_lines = []
        bolt_points = []
        if coord_mode == "BOLT CIRCLE":
            labels = {"pcd": f"PCD ({unit})", "holes": "HOLE COUNT", "start": "START ANGLE (DEG)"}
            for field_name in ("pcd", "holes", "start"):
                rect = coord_fields[field_name]
                label = font_small.render(labels[field_name], True, CYAN)
                screen.blit(label, (rect.x, rect.y - 30))
                pygame.draw.rect(screen, MED_GREY, rect)
                pygame.draw.rect(screen, YELLOW if field_name == active_coord_field else WHITE, rect, 3)
                value_text = font_small.render(coord_values[field_name] or "Enter", True, WHITE)
                screen.blit(value_text, value_text.get_rect(center=rect.center))
            if all(coord_values[name] for name in ("pcd", "holes", "start")):
                try:
                    hole_value = float(coord_values["holes"])
                    if not hole_value.is_integer() or hole_value < 2 or hole_value > 24:
                        raise ValueError("Use a whole hole count from 2 to 24")
                    bolt_points = bolt_circle_coordinates(
                        float(coord_values["pcd"]), int(hole_value), float(coord_values["start"])
                    )
                except ValueError as error:
                    result_lines = [(str(error), RED)]
        else:
            field_labels = {"first": f"FIRST DRO VALUE ({unit})", "second": f"SECOND DRO VALUE ({unit})"}
            for field_name in ("first", "second"):
                rect = coord_fields[field_name]
                label = font_small.render(field_labels[field_name], True, CYAN)
                screen.blit(label, (rect.x, rect.y - 30))
                pygame.draw.rect(screen, MED_GREY, rect)
                pygame.draw.rect(screen, YELLOW if field_name == active_coord_field else WHITE, rect, 3)
                value_text = font_medium.render(coord_values[field_name] or "Enter value", True, WHITE)
                screen.blit(value_text, value_text.get_rect(midleft=(rect.x + 20, rect.centery)))
            if coord_values["first"] and coord_values["second"]:
                try:
                    first_value = float(coord_values["first"])
                    second_value = float(coord_values["second"])
                    if coord_mode == "MIDPOINT":
                        result_lines = [(f"MIDPOINT: {coordinate_midpoint(first_value, second_value):.4f} {unit}", GREEN)]
                    else:
                        result_lines = [(f"SHOULDER DISTANCE: {shoulder_distance(first_value, second_value):.4f} {unit}", GREEN)]
                except ValueError as error:
                    result_lines = [(str(error), RED)]

        for key, rect in keypad_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            key_text = font_medium.render(key, True, WHITE)
            screen.blit(key_text, key_text.get_rect(center=rect.center))
        clear_rect = coord_buttons["CLEAR"]
        pygame.draw.rect(screen, MED_GREY, clear_rect)
        pygame.draw.rect(screen, WHITE, clear_rect, 2)
        clear_text = font_small.render("CLEAR ACTIVE FIELD", True, WHITE)
        screen.blit(clear_text, clear_text.get_rect(center=clear_rect.center))

        if coord_mode == "BOLT CIRCLE":
            if bolt_points:
                for point_index, (x_value, y_value) in enumerate(bolt_points):
                    column = point_index // 12
                    row = point_index % 12
                    point_text = font_small.render(
                        f"{point_index + 1:02d}  X {x_value:.3f}  Y {y_value:.3f} {unit}", True, GREEN
                    )
                    screen.blit(point_text, (50 + column * 330, 300 + row * 29))
            elif not result_lines:
                result_lines = [("Enter PCD, hole count, and start angle.", WHITE)]
            screen.blit(font_small.render("Coordinates are relative to center; angle advances counterclockwise from +X.", True, WHITE), (50, 665))
        elif not result_lines:
            result_lines = [("Enter both values to calculate.", WHITE)]
        for line_index, (line, color) in enumerate(result_lines):
            result_text = font_medium.render(line, True, color)
            screen.blit(result_text, (50, 440 + line_index * 48))

        back_rect = coord_buttons["BACK"]
        pygame.draw.rect(screen, RED, back_rect)
        pygame.draw.rect(screen, WHITE, back_rect, 2)
        back_text = font_medium.render("BACK", True, WHITE)
        screen.blit(back_text, back_text.get_rect(center=back_rect.center))

    elif current_state == STATE_SPEED:
        if clicked:
            if speed_buttons["BACK"].collidepoint(pos):
                current_state = STATE_MAIN_DRO
            elif speed_drive_button.collidepoint(pos):
                speed_drive_mode = "BACK GEAR" if speed_drive_mode == "BELT DRIVE" else "BELT DRIVE"
            elif speed_range_button.collidepoint(pos):
                speed_range_mode = "HIGH RANGE" if speed_range_mode == "LOW RANGE" else "LOW RANGE"
            elif speed_material_button.collidepoint(pos):
                speed_material_index = (speed_material_index + 1) % len(speed_material_names)
                material_name = speed_material_names[speed_material_index]
                speed_values["sfm"] = str(HSS_SURFACE_SPEED_SFM[material_name])
            else:
                for field_name, rect in speed_fields.items():
                    if rect.collidepoint(pos):
                        active_speed_field = field_name
                        break
                else:
                    if speed_buttons["CLEAR"].collidepoint(pos):
                        speed_values[active_speed_field] = ""
                    else:
                        for key, rect in keypad_buttons.items():
                            if rect.collidepoint(pos):
                                value = speed_values[active_speed_field]
                                if key == "DEL":
                                    speed_values[active_speed_field] = value[:-1]
                                elif key == ".":
                                    if "." not in value:
                                        speed_values[active_speed_field] = value + "."
                                elif len(value) < 12:
                                    speed_values[active_speed_field] = value + key
                                break

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("CUTTING SPEED / RPM", True, YELLOW), (50, 35))
        diameter_unit = "mm" if is_metric else "in"
        speed_labels = {"diameter": f"WORK DIAMETER ({diameter_unit})", "sfm": "SURFACE SPEED (SFM)"}
        for field_name, rect in speed_fields.items():
            label = font_small.render(speed_labels[field_name], True, CYAN)
            screen.blit(label, (rect.x, rect.y - 32))
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, YELLOW if field_name == active_speed_field else WHITE, rect, 3)
            value_text = font_medium.render(speed_values[field_name] or "0", True, WHITE)
            screen.blit(value_text, value_text.get_rect(midleft=(rect.x + 20, rect.centery)))

        pygame.draw.rect(screen, MED_GREY, speed_material_button)
        pygame.draw.rect(screen, WHITE, speed_material_button, 2)
        material_name = speed_material_names[speed_material_index]
        material_text = font_small.render(f"HSS PRESET: {material_name}  {HSS_SURFACE_SPEED_SFM[material_name]} SFM", True, WHITE)
        screen.blit(material_text, material_text.get_rect(center=speed_material_button.center))

        for rect, label in (
            (speed_drive_button, f"DRIVE: {speed_drive_mode}"),
            (speed_range_button, f"RANGE: {speed_range_mode}"),
        ):
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, CYAN, rect, 2)
            control_text = font_small.render(label, True, WHITE)
            screen.blit(control_text, control_text.get_rect(center=rect.center))

        for key, rect in keypad_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            key_text = font_medium.render(key, True, WHITE)
            screen.blit(key_text, key_text.get_rect(center=rect.center))
        clear_rect = speed_buttons["CLEAR"]
        pygame.draw.rect(screen, MED_GREY, clear_rect)
        pygame.draw.rect(screen, WHITE, clear_rect, 2)
        clear_text = font_small.render("CLEAR ACTIVE FIELD", True, WHITE)
        screen.blit(clear_text, clear_text.get_rect(center=clear_rect.center))

        if speed_values["diameter"] and speed_values["sfm"]:
            try:
                target_rpm = spindle_rpm_for_surface_speed(
                    float(speed_values["diameter"]), float(speed_values["sfm"]), metric=is_metric
                )
                step_recommendation = recommend_spindle_step(target_rpm, speed_drive_mode, speed_range_mode)
                speed_result = f"TARGET: {target_rpm:.0f} RPM"
                speed_result_color = GREEN
                if step_recommendation is None:
                    available = SPINDLE_SPEED_STEPS[(speed_drive_mode, speed_range_mode)]
                    recommendation_text = f"BELOW RANGE: minimum is Step 1 at {available[0]} RPM"
                    recommendation_color = RED
                else:
                    maximum_text = " (MAX AVAILABLE)" if step_recommendation["at_maximum"] else ""
                    recommendation_text = (
                        f"USE STEP {step_recommendation['step']} "
                        f"({step_recommendation['spindle']} spindle pulley): "
                        f"{step_recommendation['rpm']} RPM{maximum_text}"
                    )
                    recommendation_color = CYAN
            except ValueError as error:
                speed_result = str(error)
                speed_result_color = RED
                recommendation_text = ""
                recommendation_color = RED
        else:
            speed_result = "Enter work diameter and surface speed."
            speed_result_color = WHITE
            recommendation_text = ""
            recommendation_color = WHITE
        result_text = font_small.render(speed_result, True, speed_result_color)
        screen.blit(result_text, (50, 585))
        recommendation_surface = font_small.render(recommendation_text, True, recommendation_color)
        screen.blit(recommendation_surface, (50, 615))
        if speed_drive_mode == "BACK GEAR" and speed_range_mode == "HIGH RANGE":
            note_text = "HIGH-RANGE BACK-GEAR values are starred on the supplied chart; verify its footnote."
        else:
            note_text = "Change belt or engage back gear only with the spindle stopped."
        speed_note = font_small.render(note_text, True, WHITE)
        screen.blit(speed_note, (50, 650))
        back_rect = speed_buttons["BACK"]
        pygame.draw.rect(screen, RED, back_rect)
        pygame.draw.rect(screen, WHITE, back_rect, 2)
        back_text = font_medium.render("BACK", True, WHITE)
        screen.blit(back_text, back_text.get_rect(center=back_rect.center))

    elif current_state == STATE_THREAD:
        if clicked:
            if thread_buttons["BACK"].collidepoint(pos):
                current_state = STATE_MAIN_DRO
            elif thread_input_rect.collidepoint(pos):
                pass
            elif thread_buttons["CLEAR"].collidepoint(pos):
                thread_input = ""
            else:
                for key, rect in keypad_buttons.items():
                    if rect.collidepoint(pos):
                        if key == "DEL":
                            thread_input = thread_input[:-1]
                        elif key == ".":
                            if "." not in thread_input:
                                thread_input += "."
                        elif len(thread_input) < 12:
                            thread_input += key
                        break

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("QUICK-CHANGE THREAD CHART", True, YELLOW), (50, 35))
        screen.blit(font_small.render("DESIRED THREADS PER INCH (TPI)", True, CYAN), (50, 125))
        pygame.draw.rect(screen, MED_GREY, thread_input_rect)
        pygame.draw.rect(screen, YELLOW, thread_input_rect, 3)
        tpi_text = font_medium.render(thread_input or "Enter TPI", True, WHITE)
        screen.blit(tpi_text, tpi_text.get_rect(midleft=(thread_input_rect.x + 20, thread_input_rect.centery)))

        for key, rect in keypad_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            key_text = font_medium.render(key, True, WHITE)
            screen.blit(key_text, key_text.get_rect(center=rect.center))

        clear_rect = thread_buttons["CLEAR"]
        pygame.draw.rect(screen, MED_GREY, clear_rect)
        pygame.draw.rect(screen, WHITE, clear_rect, 2)
        clear_text = font_small.render("CLEAR TPI", True, WHITE)
        screen.blit(clear_text, clear_text.get_rect(center=clear_rect.center))

        if not thread_input:
            result_lines = [("Enter a pitch shown on the gearbox chart.", WHITE)]
        else:
            try:
                setting = thread_setting_for(thread_input)
            except ValueError as error:
                setting = None
                result_lines = [(str(error), RED)]
            else:
                if setting is None:
                    result_lines = [("TPI not listed on this gearbox chart.", RED)]
                else:
                    feed_rates = feed_rates_for(setting["tpi"], rpm, metric=is_metric)
                    feed_unit = "mm" if is_metric else "in"
                    result_lines = [
                        (f"{setting['tpi']:g} TPI", GREEN),
                        (f"STUD GEAR: {setting['stud_gear']}", WHITE),
                        (f"LEFT-HAND TUMBLER: {setting['tumbler']}", WHITE),
                        (f"SELECTOR COLUMN: {setting['selector_column']} (left to right)", WHITE),
                        (f"LONG FEED: {feed_rates['longitudinal_per_rev']:.4f} {feed_unit}/rev  |  {feed_rates['longitudinal_per_min']:.1f} {feed_unit}/min", CYAN),
                        (f"CROSS FEED (1/3): {feed_rates['cross_per_rev']:.4f} {feed_unit}/rev  |  {feed_rates['cross_per_min']:.1f} {feed_unit}/min", CYAN),
                    ]
        for line_index, (line, color) in enumerate(result_lines):
            result_text = font_small.render(line, True, color)
            screen.blit(result_text, (50, 295 + line_index * 38))
        note = font_small.render("Stop spindle before changing gears. Verify the first thread with a pitch gauge.", True, WHITE)
        screen.blit(note, (50, 535))

        back_rect = thread_buttons["BACK"]
        pygame.draw.rect(screen, RED, back_rect)
        pygame.draw.rect(screen, WHITE, back_rect, 2)
        back_text = font_medium.render("BACK", True, WHITE)
        screen.blit(back_text, back_text.get_rect(center=back_rect.center))

    elif current_state == STATE_TAPER:
        if clicked:
            if taper_buttons["BACK"].collidepoint(pos):
                current_state = STATE_MAIN_DRO
            else:
                for field_name, rect in taper_fields.items():
                    if rect.collidepoint(pos):
                        active_taper_field = field_name
                        break
                else:
                    for key, rect in keypad_buttons.items():
                        if rect.collidepoint(pos):
                            value = taper_values[active_taper_field]
                            if key == "DEL":
                                taper_values[active_taper_field] = value[:-1]
                            elif key == ".":
                                if "." not in value:
                                    taper_values[active_taper_field] = value + "."
                            elif len(value) < 12:
                                taper_values[active_taper_field] = value + key
                            break
                    else:
                        if taper_buttons["CLEAR"].collidepoint(pos):
                            taper_values[active_taper_field] = ""

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("COMPOUND REST TAPER CALCULATOR", True, YELLOW), (50, 35))
        unit = "mm" if is_metric else "in"
        field_labels = {
            "large": f"LARGE DIAMETER ({unit})",
            "small": f"SMALL DIAMETER ({unit})",
            "length": f"AXIAL TAPER LENGTH ({unit})"
        }
        for field_name, rect in taper_fields.items():
            label = font_small.render(field_labels[field_name], True, CYAN)
            screen.blit(label, (rect.x, rect.y - 32))
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, YELLOW if field_name == active_taper_field else WHITE, rect, 3)
            value_text = font_medium.render(taper_values[field_name] or "0", True, WHITE)
            screen.blit(value_text, value_text.get_rect(midleft=(rect.x + 20, rect.centery)))

        for key, rect in keypad_buttons.items():
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            label = font_medium.render(key, True, WHITE)
            screen.blit(label, label.get_rect(center=rect.center))

        clear_rect = taper_buttons["CLEAR"]
        pygame.draw.rect(screen, MED_GREY, clear_rect)
        pygame.draw.rect(screen, WHITE, clear_rect, 2)
        clear_label = font_small.render("CLEAR ACTIVE FIELD", True, WHITE)
        screen.blit(clear_label, clear_label.get_rect(center=clear_rect.center))

        if all(taper_values[name] for name in ("large", "small", "length")):
            try:
                angle = compound_rest_angle(
                    float(taper_values["large"]),
                    float(taper_values["small"]),
                    float(taper_values["length"])
                )
                angle_text = f"COMPOUND SETTING: {angle:.4f} degrees"
                angle_color = GREEN
            except ValueError as error:
                angle_text = str(error)
                angle_color = RED
        else:
            angle_text = "Enter all three dimensions"
            angle_color = WHITE
        angle_surface = font_medium.render(angle_text, True, angle_color)
        screen.blit(angle_surface, (50, 500))
        formula = font_small.render("Angle from spindle axis = atan(|D1 - D2| / (2 x L))", True, WHITE)
        screen.blit(formula, (50, 555))

        back_rect = taper_buttons["BACK"]
        pygame.draw.rect(screen, RED, back_rect)
        pygame.draw.rect(screen, WHITE, back_rect, 2)
        back_label = font_medium.render("BACK", True, WHITE)
        screen.blit(back_label, back_label.get_rect(center=back_rect.center))

    elif current_state == STATE_SETUP_MENU:
        # --- PARAMETER CONFIGURATION SCREEN LOGIC ---
        if clicked:
            if setup_buttons["BACK_MAIN"].collidepoint(pos):
                current_state = STATE_MAIN_DRO # SAVE AND RETURN HOME
            elif setup_buttons["RES_TOGGLE"].collidepoint(pos):
                # Cycle display step tiers smoothly
                if resolution_tier == 0.0005: resolution_tier = 0.0001
                elif resolution_tier == 0.0001: resolution_tier = 0.0010
                else: resolution_tier = 0.0005
            elif setup_buttons["COMP_X_UP"].collidepoint(pos):
                x_linear_error_comp += 0.0001
            elif setup_buttons["COMP_X_DN"].collidepoint(pos):
                x_linear_error_comp -= 0.0001
            elif setup_buttons["COMP_Z_UP"].collidepoint(pos):
                z_linear_error_comp += 0.0001
            elif setup_buttons["COMP_Z_DN"].collidepoint(pos):
                z_linear_error_comp -= 0.0001

        # DRAW SETUP INTERFACE DASHBOARD
        draw_industrial_background(screen, width, height)
        
        # Section Titles
        screen.blit(font_medium.render("SYSTEM SETUP MENU", True, YELLOW), (50, 40))
        
        # 1. Resolution Management Display block
        pygame.draw.rect(screen, MED_GREY, setup_buttons["RES_TOGGLE"])
        pygame.draw.rect(screen, WHITE, setup_buttons["RES_TOGGLE"], 2)
        screen.blit(font_small.render(f"SET STEP RES: {resolution_tier: .4f} in", True, WHITE), (70, 165))
        
        # 2. X Axis Scale Calibration Tuning blocks
        screen.blit(font_small.render(f"X-Scale Compensation Matrix Factor: {x_linear_error_comp: .4f}", True, WHITE), (50, 260))
        pygame.draw.rect(screen, MED_GREY, setup_buttons["COMP_X_UP"])
        pygame.draw.rect(screen, WHITE, setup_buttons["COMP_X_UP"], 2)
        screen.blit(font_small.render("+ 0.0001", True, GREEN), (75, 315))
        
        pygame.draw.rect(screen, MED_GREY, setup_buttons["COMP_X_DN"])
        pygame.draw.rect(screen, WHITE, setup_buttons["COMP_X_DN"], 2)
        screen.blit(font_small.render("- 0.0001", True, RED), (235, 315))

        # 3. Z Axis Scale Calibration Tuning blocks
        screen.blit(font_small.render(f"Z-Scale Compensation Matrix Factor: {z_linear_error_comp: .4f}", True, WHITE), (50, 410))
        pygame.draw.rect(screen, MED_GREY, setup_buttons["COMP_Z_UP"])
        pygame.draw.rect(screen, WHITE, setup_buttons["COMP_Z_UP"], 2)
        screen.blit(font_small.render("+ 0.0001", True, GREEN), (75, 465))
        
        pygame.draw.rect(screen, MED_GREY, setup_buttons["COMP_Z_DN"])
        pygame.draw.rect(screen, WHITE, setup_buttons["COMP_Z_DN"], 2)
        screen.blit(font_small.render("- 0.0001", True, RED), (235, 465))

        # 4. Save and Exit button
        pygame.draw.rect(screen, RED, setup_buttons["BACK_MAIN"])
        pygame.draw.rect(screen, WHITE, setup_buttons["BACK_MAIN"], 2)
        lbl_save = font_medium.render("SAVE & EXIT", True, WHITE)
        screen.blit(lbl_save, lbl_save.get_rect(center=setup_buttons["BACK_MAIN"].center))

    elif current_state == STATE_TOOL_SETUP:
        if clicked:
            if tool_setup_buttons["BACK"].collidepoint(pos):
                current_state = STATE_MAIN_DRO
            elif tool_setup_buttons["PREVIOUS"].collidepoint(pos):
                current_tool_id = 9 if current_tool_id == 1 else current_tool_id - 1
            elif tool_setup_buttons["NEXT"].collidepoint(pos):
                current_tool_id = 1 if current_tool_id >= 9 else current_tool_id + 1
            elif tool_setup_buttons["CAPTURE"].collidepoint(pos):
                if DEMO_MODE:
                    connection_status = "Live Pico required for tool capture"
                elif current_tool_id != 1 and 1 not in tool_touch_positions:
                    connection_status = "Capture T-1 master reference first"
                else:
                    tool_touch_positions[current_tool_id] = (x_pulses, z_pulses)
                    try:
                        save_tool_touch_positions(TOOL_OFFSETS_FILE, tool_touch_positions)
                        connection_status = f"T-{current_tool_id} touch-off saved"
                    except OSError:
                        connection_status = "Could not save tool touch-off"

        draw_industrial_background(screen, width, height)
        screen.blit(font_medium.render("TOOL OFFSET SETUP", True, YELLOW), (50, 40))
        screen.blit(font_large.render(f"T-{current_tool_id}", True, WHITE), (50, 110))

        for name, label in (("PREVIOUS", "PREV"), ("NEXT", "NEXT")):
            rect = tool_setup_buttons[name]
            pygame.draw.rect(screen, MED_GREY, rect)
            pygame.draw.rect(screen, WHITE, rect, 2)
            text = font_small.render(label, True, WHITE)
            screen.blit(text, text.get_rect(center=rect.center))

        screen.blit(font_small.render("Touch T-1 to the datum and capture it as master.", True, WHITE), (50, 245))
        screen.blit(font_small.render("Touch each other tool to the same datum, then capture.", True, WHITE), (50, 285))
        tool_offset = tool_offset_for(current_tool_id, tool_touch_positions)
        if current_tool_id == 1 and 1 in tool_touch_positions:
            offset_text = "MASTER REFERENCE SET"
        elif tool_offset is None:
            offset_text = "OFFSET NOT SET"
        else:
            x_offset = tool_offset[0] / PULSES_PER_INCH
            z_offset = tool_offset[1] / PULSES_PER_INCH
            if is_metric:
                x_offset *= 25.4
                z_offset *= 25.4
            if is_diameter_mode:
                x_offset *= 2
            unit = "mm" if is_metric else "in"
            offset_text = f"X OFFSET {x_offset:.4f} {unit}    Z OFFSET {z_offset:.4f} {unit}"
        screen.blit(font_small.render(offset_text, True, CYAN), (50, 335))

        capture_rect = tool_setup_buttons["CAPTURE"]
        capture_color = MED_GREY if DEMO_MODE else GREEN
        pygame.draw.rect(screen, capture_color, capture_rect)
        pygame.draw.rect(screen, WHITE, capture_rect, 2)
        if DEMO_MODE:
            capture_label = "LIVE PICO REQUIRED"
        else:
            capture_label = "CAPTURE MASTER" if current_tool_id == 1 else "CAPTURE TOOL"
        capture_text = font_small.render(capture_label, True, WHITE if DEMO_MODE else BLACK)
        screen.blit(capture_text, capture_text.get_rect(center=capture_rect.center))

        back_rect = tool_setup_buttons["BACK"]
        pygame.draw.rect(screen, RED, back_rect)
        pygame.draw.rect(screen, WHITE, back_rect, 2)
        back_text = font_medium.render("BACK", True, WHITE)
        screen.blit(back_text, back_text.get_rect(center=back_rect.center))

    pygame.display.flip()
    clock.tick(60)

if __name__ == "__main__":
    if serial_connection is not None:
        serial_connection.close()
    pygame.quit()
