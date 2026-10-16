import math
import sys

import pygame


def main():
    DEMO_MODE = True
    PULSES_PER_INCH = 25400.0

    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    pygame.display.set_caption('TEST RUN - South Bend 10k Pro DRO')
    width, height = screen.get_size()

    BLACK = (10, 10, 10)
    GREY = (35, 35, 35)
    LIGHT_GREY = (70, 70, 70)
    CYAN = (0, 255, 255)
    YELLOW = (255, 255, 0)
    WHITE = (240, 240, 240)
    GREEN = (0, 255, 0)
    MAGENTA = (255, 0, 255)

    font_large = pygame.font.SysFont('courier', int(height * 0.13), bold=True)
    font_medium = pygame.font.SysFont('sans', int(height * 0.05), bold=True)
    font_small = pygame.font.SysFont('sans', int(height * 0.03))

    x_pulses, z_pulses, rpm = 0, 0, 0
    is_diameter_mode = True
    is_metric = False
    is_abs_mode = True
    current_tool_id = 1

    def round_to_precision(value, metric_mode):
        if not metric_mode:
            return round(value * 2000) / 2000.0
        return round(value, 3)

    panel_x = int(width * 0.75)
    btn_w = int(width * 0.11)
    btn_h = int(height * 0.12)
    col1_x = panel_x + 10
    col2_x = panel_x + btn_w + 20

    buttons = {
        'DIA': pygame.Rect(col1_x, int(height * 0.02), btn_w, btn_h),
        'INCH/MM': pygame.Rect(col2_x, int(height * 0.02), btn_w, btn_h),
        'ZERO_X': pygame.Rect(col1_x, int(height * 0.16), btn_w, btn_h),
        'ABS/INC': pygame.Rect(col2_x, int(height * 0.16), btn_w, btn_h),
        'ZERO_Z': pygame.Rect(col1_x, int(height * 0.30), btn_w, btn_h),
        'TOOL_LIB': pygame.Rect(col2_x, int(height * 0.30), btn_w, btn_h),
        'TAPER': pygame.Rect(col1_x, int(height * 0.44), btn_w, btn_h),
        'FEED': pygame.Rect(col2_x, int(height * 0.44), btn_w, btn_h),
        'SETUP': pygame.Rect(col1_x, int(height * 0.58), btn_w * 2 + 10, btn_h),
    }

    running = True
    clock = pygame.time.Clock()
    frame_counter = 0

    while running:
        frame_counter += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos
                if buttons['DIA'].collidepoint(pos):
                    is_diameter_mode = not is_diameter_mode
                elif buttons['INCH/MM'].collidepoint(pos):
                    is_metric = not is_metric
                elif buttons['ABS/INC'].collidepoint(pos):
                    is_abs_mode = not is_abs_mode
                elif buttons['ZERO_X'].collidepoint(pos):
                    x_pulses = 0
                elif buttons['ZERO_Z'].collidepoint(pos):
                    z_pulses = 0
                elif buttons['TOOL_LIB'].collidepoint(pos):
                    current_tool_id = 1 if current_tool_id >= 9 else current_tool_id + 1

        if DEMO_MODE:
            if frame_counter % 2 == 0:
                x_pulses += int(15 * math.sin(frame_counter / 50.0))
                z_pulses += int(45 * math.cos(frame_counter / 100.0))
            rpm = int(720 + (25 * math.sin(frame_counter / 20.0)))

        x_val = x_pulses / PULSES_PER_INCH
        z_val = z_pulses / PULSES_PER_INCH

        if is_metric:
            x_val *= 25.4
            z_val *= 25.4
        if is_diameter_mode:
            x_val *= 2.0

        x_display = round_to_precision(x_val, is_metric)
        z_display = round_to_precision(z_val, is_metric)
        fmt = '0.3f' if is_metric else '0.4f'

        screen.fill(BLACK)
        pygame.draw.line(screen, GREY, (0, int(height * 0.33)), (panel_x, int(height * 0.33)), 4)
        pygame.draw.line(screen, GREY, (0, int(height * 0.66)), (panel_x, int(height * 0.66)), 4)
        pygame.draw.line(screen, GREY, (panel_x, 0), (panel_x, height), 4)

        screen.blit(font_medium.render('X', True, WHITE), (40, int(height * 0.08)))
        screen.blit(font_large.render(format(x_display, fmt), True, CYAN), (150, int(height * 0.04)))
        screen.blit(font_medium.render('Z', True, WHITE), (40, int(height * 0.41)))
        screen.blit(font_large.render(format(z_display, fmt), True, WHITE), (150, int(height * 0.37)))
        screen.blit(font_medium.render('SPINDLE', True, WHITE), (40, int(height * 0.74)))
        screen.blit(font_large.render(f'{rpm}', True, GREEN if rpm > 0 else LIGHT_GREY), (320, int(height * 0.70)))
        screen.blit(font_medium.render('RPM', True, GREEN if rpm > 0 else LIGHT_GREY), (width * 0.58, int(height * 0.74)))

        for btn_name, rect in buttons.items():
            b_color = GREY
            t_color = WHITE
            if btn_name == 'DIA' and is_diameter_mode:
                b_color, t_color = YELLOW, BLACK
            elif btn_name == 'INCH/MM' and is_metric:
                b_color, t_color = MAGENTA, BLACK
            elif btn_name == 'ABS/INC' and not is_abs_mode:
                b_color, t_color = CYAN, BLACK

            pygame.draw.rect(screen, b_color, rect)
            pygame.draw.rect(screen, LIGHT_GREY, rect, 2)
            label_text = f'T-{current_tool_id}' if btn_name == 'TOOL_LIB' else btn_name
            lbl = font_small.render(label_text, True, t_color)
            text_rect = lbl.get_rect(center=rect.center)
            screen.blit(lbl, text_rect)

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
