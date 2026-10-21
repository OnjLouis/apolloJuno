cmake_minimum_required(VERSION 3.20)
project(ApolloJuno VERSION 1.2 LANGUAGES C)

if(NOT WIN32 OR NOT CMAKE_SIZEOF_VOID_P EQUAL 8)
    message(FATAL_ERROR "The NVDA host requires 64-bit Windows")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

file(GLOB ENGINE_SOURCES CONFIGURE_DEPENDS
    src/board/*.c src/engine/*.c src/firmware/*.c
    src/firmware/data/*.c src/synth/*.c src/orpheus/*.c)
add_executable(ApolloJunoHost nvda/native/apollo_host.c ${ENGINE_SOURCES})
target_include_directories(ApolloJunoHost PRIVATE src)
target_compile_definitions(ApolloJunoHost PRIVATE _CRT_SECURE_NO_WARNINGS)
if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(ApolloJunoHost PRIVATE -O2 -Wall -Wextra -Werror
        -Wno-missing-field-initializers -ffp-contract=off
        "-ffile-prefix-map=${CMAKE_SOURCE_DIR}=apollo-source")
    target_link_libraries(ApolloJunoHost PRIVATE m)
elseif(MSVC)
    target_compile_options(ApolloJunoHost PRIVATE /O2 /W4)
endif()

include(CTest)
if(BUILD_TESTING)
    add_executable(OutputLevelTest nvda/tests/test_output_level.c)
    add_executable(ToneControlsTest nvda/tests/test_tone_controls.c)
    if(NOT MSVC)
        target_link_libraries(OutputLevelTest PRIVATE m)
        target_link_libraries(ToneControlsTest PRIVATE m)
    endif()
    add_test(NAME output_level COMMAND OutputLevelTest)
    add_test(NAME tone_controls COMMAND ToneControlsTest)
endif()
