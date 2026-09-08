cmake_minimum_required(VERSION 3.20)
project(apeq_ips_ole_core LANGUAGES CXX)

option(FP_CHECKED "Enable expensive field invariant checks" ON)
option(IPS_OLE_BUILD_LIBOTE_ADAPTER "Build the libOTe receiver adapter" OFF)
set(IPS_OLE_SANITIZER "" CACHE STRING "Optional sanitizer: thread or address")

if(IPS_OLE_SANITIZER STREQUAL "thread")
  add_compile_options(-fsanitize=thread -fno-omit-frame-pointer)
  add_link_options(-fsanitize=thread)
elseif(IPS_OLE_SANITIZER STREQUAL "address")
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
elseif(NOT IPS_OLE_SANITIZER STREQUAL "")
  message(FATAL_ERROR "IPS_OLE_SANITIZER must be empty, thread, or address")
endif()

find_package(OpenSSL REQUIRED)
find_package(Threads REQUIRED)
find_package(Boost REQUIRED)

add_library(ips_ole_core
  src/core.cpp
)
target_include_directories(ips_ole_core PUBLIC include)
target_compile_features(ips_ole_core PUBLIC cxx_std_20)
target_compile_options(ips_ole_core PRIVATE -Wall -Wextra -Werror)
target_link_libraries(ips_ole_core PUBLIC OpenSSL::Crypto Threads::Threads Boost::headers)
if(FP_CHECKED)
  target_compile_definitions(ips_ole_core PUBLIC FP_CHECKED=1)
endif()

add_executable(ips_ole_tests tests/test_core.cpp)
target_include_directories(ips_ole_tests PRIVATE tests/support)
target_link_libraries(ips_ole_tests PRIVATE ips_ole_core)
target_compile_options(ips_ole_tests PRIVATE -Wall -Wextra -Werror)

add_executable(ips_ole_vectors tools/vector_dump.cpp)
target_include_directories(ips_ole_vectors PRIVATE tests/support)
target_link_libraries(ips_ole_vectors PRIVATE ips_ole_core)
target_compile_options(ips_ole_vectors PRIVATE -Wall -Wextra -Werror)

enable_testing()
add_test(NAME ips_ole_core COMMAND ips_ole_tests)

if(IPS_OLE_BUILD_LIBOTE_ADAPTER)
  find_package(libOTe CONFIG REQUIRED)
  add_library(ips_ole_libote
    adapters/libote_retriever.cpp
  )
  target_include_directories(ips_ole_libote PUBLIC adapters)
  target_compile_features(ips_ole_libote PUBLIC cxx_std_20)
  target_compile_options(ips_ole_libote PRIVATE -Wall -Wextra -Werror)
  target_link_libraries(ips_ole_libote PUBLIC ips_ole_core oc::libOTe)

  add_executable(ips_ole_libote_tests tests/test_libote_retriever.cpp)
  target_compile_options(ips_ole_libote_tests PRIVATE -Wall -Wextra -Werror)
  target_link_libraries(ips_ole_libote_tests PRIVATE ips_ole_libote)
  add_test(NAME ips_ole_libote COMMAND ips_ole_libote_tests)

  add_executable(ips_ole_libote_tcp tests/test_libote_tcp.cpp)
  target_compile_options(ips_ole_libote_tcp PRIVATE -Wall -Wextra -Werror)
  target_link_libraries(ips_ole_libote_tcp PRIVATE ips_ole_libote)
endif()
