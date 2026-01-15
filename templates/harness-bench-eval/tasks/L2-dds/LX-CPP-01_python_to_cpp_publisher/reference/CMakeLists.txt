cmake_minimum_required(VERSION 3.10)
project(HelloWorldPublisher CXX)

set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Find RTI Connext DDS
if(NOT DEFINED CONNEXTDDS_DIR)
    if(DEFINED ENV{NDDSHOME})
        set(CONNEXTDDS_DIR $ENV{NDDSHOME})
    else()
        message(FATAL_ERROR "CONNEXTDDS_DIR or NDDSHOME must be set")
    endif()
endif()

list(APPEND CMAKE_MODULE_PATH "${CONNEXTDDS_DIR}/resource/cmake")
find_package(RTIConnextDDS "7.0.0" REQUIRED COMPONENTS core)

# rtiddsgen is run by the test harness before cmake
# The generated files (HelloWorld.cxx, HelloWorld.hpp, HelloWorldPlugin.cxx, HelloWorldPlugin.hpp)
# are in the source directory

# Create executable with generated type support
add_executable(publisher 
    publisher.cxx
    ${CMAKE_SOURCE_DIR}/HelloWorld.cxx
    ${CMAKE_SOURCE_DIR}/HelloWorldPlugin.cxx
)

target_include_directories(publisher PRIVATE
    ${CMAKE_SOURCE_DIR}
)

target_link_libraries(publisher 
    RTIConnextDDS::cpp2_api
)
