cmake_minimum_required(VERSION 3.15)
project(clipper2_py LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)

set(CLIPPER2_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party/Clipper2/CPP/Clipper2Lib")
if(NOT EXISTS "${CLIPPER2_DIR}/src/clipper.engine.cpp")
  message(FATAL_ERROR "third_party/Clipper2 is empty: run git submodule update --init")
endif()
# Upstream sources are compiled straight into each extension: the Z build changes the Point
# layout, so the two extensions cannot share one library.
set(CLIPPER2_SOURCES
  "${CLIPPER2_DIR}/src/clipper.engine.cpp"
  "${CLIPPER2_DIR}/src/clipper.offset.cpp"
  "${CLIPPER2_DIR}/src/clipper.rectclip.cpp"
  "${CLIPPER2_DIR}/src/clipper.triangulation.cpp")
set(BINDING_SOURCES
  src/cpp/module.cpp
  src/cpp/bind_core.cpp
  src/cpp/bind_engine.cpp
  src/cpp/bind_offset.cpp
  src/cpp/bind_misc.cpp)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)

foreach(mod _clipper2 _clipper2z)
  pybind11_add_module(${mod} ${BINDING_SOURCES} ${CLIPPER2_SOURCES})
  target_include_directories(${mod} PRIVATE "${CLIPPER2_DIR}/include" src/cpp)
  target_compile_definitions(${mod} PRIVATE CLIPPER2_PY_MODULE_NAME=${mod})
  install(TARGETS ${mod} DESTINATION clipper2)
endforeach()
target_compile_definitions(_clipper2z PRIVATE USINGZ)
