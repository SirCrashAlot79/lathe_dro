#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/irq.h"
#include "quadrature.pio.h"

// Scale pairs are independent so both machines can remain connected.
#define MILL_X_PIN_A    2
#define MILL_Z_PIN_A    4
#define MILL_Y_PIN_A    6
#define TACH_PIN        8
#define LATHE_X_PIN_A   9
#define LATHE_Z_PIN_A   11

// GP8 may use its 3.3 V pull-up only if the tach output is verified open-collector.
static constexpr uint32_t TACH_PULSES_PER_REV = 4;
static constexpr uint32_t TACH_TIMEOUT_US = 1500000;

static volatile int32_t mill_x_pulse_count = 0;
static volatile int32_t mill_y_pulse_count = 0;
static volatile int32_t mill_z_pulse_count = 0;
static volatile int32_t lathe_x_pulse_count = 0;
static volatile int32_t lathe_z_pulse_count = 0;
static volatile uint32_t last_tach_pulse_time = 0;
static volatile uint32_t pulse_delta = 0;
static volatile bool tach_pulse_initialized = false;

static uint8_t last_mill_x_state = 0;
static uint8_t last_mill_y_state = 0;
static uint8_t last_mill_z_state = 0;
static uint8_t last_lathe_x_state = 0;
static uint8_t last_lathe_z_state = 0;
static bool mill_x_state_initialized = false;
static bool mill_y_state_initialized = false;
static bool mill_z_state_initialized = false;
static bool lathe_x_state_initialized = false;
static bool lathe_z_state_initialized = false;

static const int8_t quadrature_delta[16] = {
    0, 1, -1, 0,
    -1, 0, 0, 1,
    1, 0, 0, -1,
    0, -1, 1, 0
};

static void process_axis_samples(PIO pio, uint sm, volatile int32_t *count,
                                 uint8_t *last_state, bool *initialized) {
    while (!pio_sm_is_rx_fifo_empty(pio, sm)) {
        const uint8_t state = static_cast<uint8_t>((pio_sm_get(pio, sm) >> 30) & 0x03u);
        if (!*initialized) {
            *last_state = state;
            *initialized = true;
            continue;
        }

        const int8_t delta = quadrature_delta[(*last_state << 2) | state];
        *count += delta;
        *last_state = state;
    }
}

static void pio0_irq_handler() {
    process_axis_samples(pio0, 0, &mill_x_pulse_count, &last_mill_x_state, &mill_x_state_initialized);
    process_axis_samples(pio0, 1, &mill_z_pulse_count, &last_mill_z_state, &mill_z_state_initialized);
    process_axis_samples(pio0, 2, &mill_y_pulse_count, &last_mill_y_state, &mill_y_state_initialized);
    process_axis_samples(pio0, 3, &lathe_x_pulse_count, &last_lathe_x_state, &lathe_x_state_initialized);
}

static void pio1_irq_handler() {
    process_axis_samples(pio1, 0, &lathe_z_pulse_count, &last_lathe_z_state, &lathe_z_state_initialized);
}

// Capture one falling edge per tach target. The first edge establishes a baseline.
void tach_interrupt_handler(uint gpio, uint32_t events) {
    (void)gpio;
    (void)events;
    uint32_t current_time = time_us_32();
    if (tach_pulse_initialized) {
        const uint32_t elapsed = current_time - last_tach_pulse_time;
        pulse_delta = elapsed <= TACH_TIMEOUT_US ? elapsed : 0;
    } else {
        tach_pulse_initialized = true;
        pulse_delta = 0;
    }
    last_tach_pulse_time = current_time;
}

int main() {
    stdio_init_all();

    stdio_set_translate_crlf(&stdio_usb, false);

    // 1. Initialize Spindle RPM Pin
    gpio_init(TACH_PIN);
    gpio_set_dir(TACH_PIN, GPIO_IN);
    gpio_pull_up(TACH_PIN); // 3.3 V pull-up for verified NPN sinking/open-collector output.
    gpio_set_irq_enabled_with_callback(TACH_PIN, GPIO_IRQ_EDGE_FALL, true, &tach_interrupt_handler);

    // PIO0 has four state machines; use PIO1 for the fifth independent encoder.
    const uint pio0_offset = pio_add_program(pio0, &quadrature_program);
    const uint pio1_offset = pio_add_program(pio1, &quadrature_program);
    for (uint sm = 0; sm < 4; ++sm) {
        pio_sm_claim(pio0, sm);
        pio_set_irq0_source_enabled(pio0, static_cast<pio_interrupt_source_t>(pis_sm0_rx_fifo_not_empty + sm), true);
    }
    pio_sm_claim(pio1, 0);
    pio_set_irq0_source_enabled(pio1, pis_sm0_rx_fifo_not_empty, true);
    irq_set_exclusive_handler(PIO0_IRQ_0, pio0_irq_handler);
    irq_set_exclusive_handler(PIO1_IRQ_0, pio1_irq_handler);
    irq_set_enabled(PIO0_IRQ_0, true);
    irq_set_enabled(PIO1_IRQ_0, true);

    quadrature_program_init(pio0, 0, pio0_offset, MILL_X_PIN_A);
    quadrature_program_init(pio0, 1, pio0_offset, MILL_Z_PIN_A);
    quadrature_program_init(pio0, 2, pio0_offset, MILL_Y_PIN_A);
    quadrature_program_init(pio0, 3, pio0_offset, LATHE_X_PIN_A);
    quadrature_program_init(pio1, 0, pio1_offset, LATHE_Z_PIN_A);

    uint32_t last_serial_tx = 0;
    uint32_t current_rpm = 0;

    while (true) {
        uint32_t now = time_us_32() / 1000u;

        // Ignore the first edge interval and clear RPM after a long gap between targets.
        const uint32_t tach_now_us = time_us_32();
        const uint32_t tach_last_pulse_us = last_tach_pulse_time;
        const uint32_t tach_period_us = pulse_delta;
        if (!tach_pulse_initialized || tach_now_us - tach_last_pulse_us > TACH_TIMEOUT_US) {
            current_rpm = 0;
        } else if (tach_period_us > 0) {
            current_rpm = 60000000u / (tach_period_us * TACH_PULSES_PER_REV);
        }

        // 4. Stream Packet to Ubuntu Laptop at 60Hz Interval (Every 16ms)
        if (now - last_serial_tx >= 16) {
            printf("LX:%d,LZ:%d,MX:%d,MY:%d,MZ:%d,RPM:%u\n",
                   lathe_x_pulse_count, lathe_z_pulse_count,
                   mill_x_pulse_count, mill_y_pulse_count, mill_z_pulse_count,
                   current_rpm);
            last_serial_tx = now;
        }

        // Optional serial reset commands for a direct firmware-side zero.
        int input_char = getchar_timeout_us(0);
        if (input_char != PICO_ERROR_TIMEOUT) {
            static char serial_buffer[32];
            static int buffer_index = 0;

            if (input_char == '\n' || input_char == '\r') {
                serial_buffer[buffer_index] = '\0';
                // Preserve the legacy zero commands for both machine profiles.
                if (strcmp(serial_buffer, "ZERO_X") == 0) {
                    lathe_x_pulse_count = 0;
                    mill_x_pulse_count = 0;
                } else if (strcmp(serial_buffer, "ZERO_Z") == 0) {
                    lathe_z_pulse_count = 0;
                    mill_z_pulse_count = 0;
                } else if (strcmp(serial_buffer, "ZERO_Y") == 0) {
                    mill_y_pulse_count = 0;
                }
                buffer_index = 0; // Clear string tracking
            } else if (buffer_index < 31) {
                serial_buffer[buffer_index++] = (char)input_char;
            }
        }

        sleep_ms(1);
    }
    return 0;
}
