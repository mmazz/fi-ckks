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

# ---------------------------------------------------------------- core
add_library(fi_core STATIC
    core/args.cpp
    core/campaign_helper.cpp
    core/logger.cpp
    core/metrics.cpp
    core/registry.cpp
    core/pipeline.cpp
)
target_include_directories(fi_core PUBLIC ${CMAKE_SOURCE_DIR}/core)

enable_testing()

add_executable(test_pipeline apps/tools/test_pipeline.cpp)
target_link_libraries(test_pipeline PRIVATE fi_core)
add_test(NAME pipeline COMMAND test_pipeline)

# Tests: header de asserts propio (tests/check.h), sin dependencias externas.
add_library(fi_test_support INTERFACE)
target_include_directories(fi_test_support INTERFACE ${CMAKE_SOURCE_DIR}/tests)
# ---------------------------------------------------------------- HEAAN
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

    # Puente Injector <-> hook del fork. Lo comparten el backend y los workloads HEAAN.
    add_library(fi_heaan_inject STATIC backends/heaan_inject.cpp)
    target_include_directories(fi_heaan_inject PUBLIC ${CMAKE_SOURCE_DIR}/backends)
    target_link_libraries(fi_heaan_inject PUBLIC fi_core heaan_lib)

    add_library(fi_backend_heaan STATIC backends/heaan.cpp)
    target_link_libraries(fi_backend_heaan PUBLIC fi_heaan_inject)

    add_executable(fi_heaan apps/fi_main.cpp)
    target_link_libraries(fi_heaan PRIVATE fi_backend_heaan)

    add_executable(fi_test_heaan tests/backend_tests.cpp)
    target_link_libraries(fi_test_heaan PRIVATE fi_backend_heaan fi_test_support)
    add_test(NAME heaan_backend COMMAND fi_test_heaan
             --logN 4 --logQ 120 --logDelta 30 --logSlots 2 --bitsPerCoeff 128
             --pipeline "add$<SEMICOLON> mul$<SEMICOLON> rot 1" --seed 7 --seed_input 3)

    add_executable(fi_test_heaan_ct tests/heaan_ciphertext_test.cpp)
    target_link_libraries(fi_test_heaan_ct PRIVATE fi_heaan_inject fi_test_support)
    add_test(NAME heaan_ciphertext COMMAND fi_test_heaan_ct)
endif()

# ---------------------------------------------------------------- OpenFHE
if(WITH_OPENFHE)
    find_package(OpenFHE CONFIG REQUIRED
        PATHS ${THIRD_PARTY}/openfhe-PRNG-Control/install/lib/OpenFHE
        NO_DEFAULT_PATH)
    message(STATUS "OpenFHE flags: ${OpenFHE_CXX_FLAGS}")

    separate_arguments(OFHE_CXX_FLAGS UNIX_COMMAND "${OpenFHE_CXX_FLAGS}")
    separate_arguments(OFHE_LD_FLAGS  UNIX_COMMAND "${OpenFHE_EXE_LINKER_FLAGS}")
    list(REMOVE_ITEM OFHE_CXX_FLAGS -Werror)   # no queremos que un warning nuestro rompa el build

    # Todo lo que hace falta para compilar y linkear contra OpenFHE, en un solo target.
    add_library(openfhe_lib INTERFACE)
    target_compile_options(openfhe_lib INTERFACE ${OFHE_CXX_FLAGS})
    target_include_directories(openfhe_lib INTERFACE
        ${OpenFHE_INCLUDE}
        ${OpenFHE_INCLUDE}/third-party/include
        ${OpenFHE_INCLUDE}/core
        ${OpenFHE_INCLUDE}/pke
        ${OpenFHE_INCLUDE}/binfhe)
    target_link_directories(openfhe_lib INTERFACE ${OpenFHE_LIBDIR})
    target_link_libraries(openfhe_lib INTERFACE ${OpenFHE_SHARED_LIBRARIES})
    target_link_options(openfhe_lib INTERFACE -Wl,--no-as-needed ${OFHE_LD_FLAGS})

    add_library(fi_openfhe_inject STATIC backends/openfhe_inject.cpp)
    target_include_directories(fi_openfhe_inject PUBLIC ${CMAKE_SOURCE_DIR}/backends)
    target_link_libraries(fi_openfhe_inject PUBLIC fi_core openfhe_lib)

    add_library(fi_backend_openfhe STATIC backends/openfhe.cpp)
    target_link_libraries(fi_backend_openfhe PUBLIC fi_openfhe_inject)

    add_executable(fi_openfhe apps/fi_main.cpp)
    target_link_libraries(fi_openfhe PRIVATE fi_backend_openfhe)
    set_target_properties(fi_openfhe PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})

    add_executable(fi_test_openfhe tests/backend_tests.cpp)
    target_link_libraries(fi_test_openfhe PRIVATE fi_backend_openfhe fi_test_support)
    set_target_properties(fi_test_openfhe PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})
    add_test(NAME openfhe_backend COMMAND fi_test_openfhe
             --logN 4 --logQ 60 --logDelta 40 --logSlots 2 --bitsPerCoeff 64
             --mult_depth 1 --withNTT 1 --pipeline "add$<SEMICOLON> mul" --seed 7 --seed_input 3)

    add_executable(fi_test_openfhe_ct tests/openfhe_ciphertext_test.cpp)
    target_link_libraries(fi_test_openfhe_ct PRIVATE fi_openfhe_inject fi_test_support)
    set_target_properties(fi_test_openfhe_ct PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})
    add_test(NAME openfhe_ciphertext COMMAND fi_test_openfhe_ct)

endif()

# ---------------------------------------------------------------- workload NN
add_library(fi_nn_plain STATIC workloads/nn/mnist.cpp)
target_include_directories(fi_nn_plain PUBLIC ${CMAKE_SOURCE_DIR}/workloads/nn)
target_compile_definitions(fi_nn_plain PRIVATE FI_NN_DATA_DIR="${CMAKE_SOURCE_DIR}/workloads/nn/data")

if(WITH_HEAAN)
    add_library(fi_nn_heaan STATIC workloads/nn/heaan_nn.cpp)
    target_link_libraries(fi_nn_heaan PUBLIC fi_heaan_inject fi_nn_plain)
    add_executable(fi_heaan_nn apps/fi_main.cpp)
    target_link_libraries(fi_heaan_nn PRIVATE fi_nn_heaan)
    add_executable(fi_nn_metrics_heaan apps/tools/nn_metrics.cpp)
    target_link_libraries(fi_nn_metrics_heaan PRIVATE fi_nn_heaan)
endif()
if(WITH_OPENFHE)
    add_library(fi_nn_openfhe STATIC workloads/nn/openfhe_nn.cpp)
    target_link_libraries(fi_nn_openfhe PUBLIC fi_openfhe_inject fi_nn_plain)
    add_executable(fi_openfhe_nn apps/fi_main.cpp)
    target_link_libraries(fi_openfhe_nn PRIVATE fi_nn_openfhe)
    set_target_properties(fi_openfhe_nn PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})
    add_executable(fi_nn_metrics_openfhe apps/tools/nn_metrics.cpp)
    target_link_libraries(fi_nn_metrics_openfhe PRIVATE fi_nn_openfhe)
    set_target_properties(fi_nn_metrics_openfhe PROPERTIES BUILD_RPATH ${OpenFHE_LIBDIR})
endif()
