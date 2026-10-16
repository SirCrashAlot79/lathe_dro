cmake_minimum_required(VERSION 3.13)
set(PICO_BOARD pico2 CACHE STRING "Raspberry Pi Pico board" FORCE)
include(pico_sdk_import.cmake)
project(lathe_dro_pico C CXX ASM)
pico_sdk_init()

add_executable(lathe_dro_pico main.cpp)

# Direct the SDK to run the PIO compiler to create 'quadrature.pio.h' dynamically
pico_generate_pio_header(lathe_dro_pico ${CMAKE_CURRENT_LIST_DIR}/quadrature.pio)

target_link_libraries(lathe_dro_pico pico_stdlib hardware_pio hardware_irq)
pico_enable_stdio_usb(lathe_dro_pico 1)
pico_enable_stdio_uart(lathe_dro_pico 0)
pico_add_extra_outputs(lathe_dro_pico)
