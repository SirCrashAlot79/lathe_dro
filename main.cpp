#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/pio.h"
#include "hardware/irq.h"
#include "quadrature.pio.h"

// --- PIN ASSIGNMENTS ---
// Linear Scales (Must be sequential pairs for PIO reading)
#define SCALE_X_PIN_A   2   // X-Axis Channel A (Pin 3 is Channel B)
#define SCALE_Z_PIN_A   4   // Z-Axis Channel A (Pin 5 is Channel B)
#define SCALE_Y_PIN_A   6   // Y-Axis Channel A (Pin 7 is Channel B)

// Spindle tach input for LJ12A3-4-Z/BX NPN NO sensor. Power sensor from 6-36 V;
// GP8 may use its 3.3 V pull-up only if the sensor output is verified open-collector.
#define TACH_PIN        8
static constexpr uint32_t TACH_PULSES_PER_REV = 4;
static constexpr uint32_t TACH_TIMEOUT_US = 1500000;

static volatile int32_t x_pulse_count = 0;
static volatile int32_t y_pulse_count = 0;
static volatile int32_t z_pulse_count = 0;
static volatile uint32_t last_tach_pulse_time = 0;
static volatile uint32_t pulse_delta = 0;
static volatile bool tach_pulse_initialized = false;

static uint8_t last_x_state = 0;
static uint8_t last_y_state = 0;
static uint8_t last_z_state = 0;
static bool x_state_initialized = false;
static bool y_state_initialized = false;
static bool z_state_initialized = false;

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

static void pio_irq_handler() {
    process_axis_samples(pio0, 0, &x_pulse_count, &last_x_state, &x_state_initialized);
    process_axis_samples(pio0, 1, &z_pulse_count, &last_z_state, &z_state_initialized);
    process_axis_samples(pio0, 2, &y_pulse_count, &last_y_state, &y_state_initialized);
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

    // 2. Initialize the three PIO state machines and their shared RX-FIFO IRQ.
    PIO pio = pio0;
    uint offset = pio_add_program(pio, &quadrature_program);
    const uint sm_x = 0;
    const uint sm_z = 1;
    const uint sm_y = 2;
    pio_sm_claim(pio, sm_x);
    pio_sm_claim(pio, sm_z);
    pio_sm_claim(pio, sm_y);
    irq_set_exclusive_handler(PIO0_IRQ_0, pio_irq_handler);
    pio_set_irq0_source_enabled(pio, pis_sm0_rx_fifo_not_empty, true);
    pio_set_irq0_source_enabled(pio, pis_sm1_rx_fifo_not_empty, true);
    pio_set_irq0_source_enabled(pio, pis_sm2_rx_fifo_not_empty, true);
    irq_set_enabled(PIO0_IRQ_0, true);

    quadrature_program_init(pio, sm_x, offset, SCALE_X_PIN_A);
    quadrature_program_init(pio, sm_z, offset, SCALE_Z_PIN_A);
    quadrature_program_init(pio, sm_y, offset, SCALE_Y_PIN_A);

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
            // Transmit matching format expected by lathe_dro_pro.py
            printf("X:%d,Y:%d,Z:%d,RPM:%u\n",
                   x_pulse_count, y_pulse_count, z_pulse_count, current_rpm);
            last_serial_tx = now;
        }

        // Optional serial reset commands for a direct firmware-side zero.
        int input_char = getchar_timeout_us(0);
        if (input_char != PICO_ERROR_TIMEOUT) {
            static char serial_buffer[32];
            static int buffer_index = 0;

            if (input_char == '\n' || input_char == '\r') {
                serial_buffer[buffer_index] = '\0';
                // Reset coordinate memory to absolute reference zero point
                if (strcmp(serial_buffer, "ZERO_X") == 0) {
                    x_pulse_count = 0;
                } else if (strcmp(serial_buffer, "ZERO_Z") == 0) {
                    z_pulse_count = 0;
                } else if (strcmp(serial_buffer, "ZERO_Y") == 0) {
                    y_pulse_count = 0;
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
