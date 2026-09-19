# Standalone build of the differential test's reference CLI. Not part of the root project.
#   cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release && cmake --build build/ref
# The binaries land at build/ref/ref_cli and build/ref/ref_cli_z (build/ref/Release/*.exe
# with MSVC).  ref_cli_z is the same source built with USINGZ: the reference for clipper2.z.
cmake_minimum_required(VERSION 3.15)
project(clipper2_ref_cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Same optimisation level the wheel is built with; nothing that changes floating point.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

set(CLIPPER2_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/Clipper2/CPP/Clipper2Lib")
if(NOT EXISTS "${CLIPPER2_DIR}/src/clipper.engine.cpp")
  message(FATAL_ERROR "third_party/Clipper2 is empty: run git submodule update --init")
endif()

set(REF_CLI_SOURCES
  ref_cli.cpp
  "${CLIPPER2_DIR}/src/clipper.engine.cpp"
  "${CLIPPER2_DIR}/src/clipper.offset.cpp"
  "${CLIPPER2_DIR}/src/clipper.rectclip.cpp"
  "${CLIPPER2_DIR}/src/clipper.triangulation.cpp")

foreach(target ref_cli ref_cli_z)
  add_executable(${target} ${REF_CLI_SOURCES})
  target_include_directories(${target} PRIVATE "${CLIPPER2_DIR}/include")
endforeach()
target_compile_definitions(ref_cli_z PRIVATE USINGZ)
