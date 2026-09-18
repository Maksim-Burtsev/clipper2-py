# Standalone build of the differential test's reference CLI. Not part of the root project.
#   cmake -S tests/reference -B build/ref -DCMAKE_BUILD_TYPE=Release && cmake --build build/ref
# The binary lands at build/ref/ref_cli (build/ref/Release/ref_cli.exe with MSVC).
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

add_executable(ref_cli
  ref_cli.cpp
  "${CLIPPER2_DIR}/src/clipper.engine.cpp"
  "${CLIPPER2_DIR}/src/clipper.offset.cpp"
  "${CLIPPER2_DIR}/src/clipper.rectclip.cpp"
  "${CLIPPER2_DIR}/src/clipper.triangulation.cpp")
target_include_directories(ref_cli PRIVATE "${CLIPPER2_DIR}/include")
