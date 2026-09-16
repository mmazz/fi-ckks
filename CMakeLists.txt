cmake_minimum_required(VERSION 3.18)
project(fi_ckks CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

option(WITH_HEAAN   "Compilar backend HEAAN"   ON)
option(WITH_OPENFHE "Compilar backend OpenFHE" ON)

set(THIRD_PARTY ${CMAKE_SOURCE_DIR}/third_party)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

add_library(fi_core STATIC
    core/args.cpp
    core/campaign_helper.cpp
    core/logger.cpp
    core/metrics.cpp
    core/registry.cpp
    core/pipeline.cpp
)
target_include_directories(fi_core PUBLIC ${CMAKE_SOURCE_DIR}/core)

if(WITH_HEAAN)
    set(HEAAN_DIR ${THIRD_PARTY}/HEAAN-PRNG-Control)
    find_library(NTL_LIB ntl REQUIRED)
    find_library(GMP_LIB gmp REQUIRED)
    find_package(Threads REQUIRED)

    add_library(heaan_lib STATIC IMPORTED)
    set_target_properties(heaan_lib PROPERTIES
        IMPORTED_LOCATION             ${HEAAN_DIR}/lib/libHEAAN.a
        INTERFACE_INCLUDE_DIRECTORIES ${HEAAN_DIR}/src)
    target_link_libraries(heaan_lib INTERFACE ${NTL_LIB} ${GMP_LIB} Threads::Threads m)

    add_library(fi_backend_heaan STATIC backends/heaan.cpp)

    target_link_libraries(fi_backend_heaan PUBLIC fi_core heaan_lib)
endif()

if(WITH_OPENFHE)
    find_package(OpenFHE CONFIG REQUIRED
        PATHS ${THIRD_PARTY}/openfhe-PRNG-Control/install/lib/OpenFHE
        NO_DEFAULT_PATH)
    message(STATUS "OpenFHE flags: ${OpenFHE_CXX_FLAGS}")

    separate_arguments(OFHE_CXX_FLAGS UNIX_COMMAND "${OpenFHE_CXX_FLAGS}")
    separate_arguments(OFHE_LD_FLAGS  UNIX_COMMAND "${OpenFHE_EXE_LINKER_FLAGS}")

    add_library(fi_backend_openfhe STATIC backends/openfhe.cpp)
    target_compile_options(fi_backend_openfhe PRIVATE ${OFHE_CXX_FLAGS})
    target_include_directories(fi_backend_openfhe PUBLIC
        ${OpenFHE_INCLUDE}
        ${OpenFHE_INCLUDE}/third-party/include
        ${OpenFHE_INCLUDE}/core
        ${OpenFHE_INCLUDE}/pke
        ${OpenFHE_INCLUDE}/binfhe)
    target_link_directories(fi_backend_openfhe PUBLIC ${OpenFHE_LIBDIR})
    target_link_libraries(fi_backend_openfhe PUBLIC fi_core ${OpenFHE_SHARED_LIBRARIES})
endif()

if(WITH_HEAAN)
    add_executable(fi_heaan apps/fi_main.cpp)
    target_link_libraries(fi_heaan PRIVATE fi_backend_heaan)
endif()

if(WITH_OPENFHE)
    add_executable(fi_openfhe apps/fi_main.cpp)
    target_link_libraries(fi_openfhe PRIVATE fi_backend_openfhe)
    target_link_options(fi_openfhe PRIVATE -Wl,--no-as-needed ${OFHE_LD_FLAGS})
    set_target_properties(fi_openfhe PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})
endif()

add_executable(test_pipeline apps/tools/test_pipeline.cpp)
target_link_libraries(test_pipeline PRIVATE fi_core)
