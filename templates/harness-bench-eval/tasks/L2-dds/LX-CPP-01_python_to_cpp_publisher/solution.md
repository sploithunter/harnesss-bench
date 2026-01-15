# Solution: Python to C++ Publisher Translation

## HelloWorld.idl

```idl
struct HelloWorld {
    string<256> message;
    long count;
};
```

## publisher.cxx

```cpp
#include <iostream>
#include <thread>
#include <chrono>
#include <dds/dds.hpp>
#include "HelloWorld.hpp"

int main(int argc, char* argv[]) {
    int count = 10;
    int domain_id = 0;
    
    // Parse arguments
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if ((arg == "--count" || arg == "-c") && i + 1 < argc) {
            count = std::stoi(argv[++i]);
        } else if ((arg == "--domain" || arg == "-d") && i + 1 < argc) {
            domain_id = std::stoi(argv[++i]);
        }
    }
    
    // Create participant
    dds::domain::DomainParticipant participant(domain_id);
    
    // Create topic
    dds::topic::Topic<HelloWorld> topic(participant, "HelloWorld");
    
    // Create publisher
    dds::pub::Publisher publisher(participant);
    
    // Configure QoS to match Python subscriber
    dds::pub::qos::DataWriterQos writer_qos;
    writer_qos << dds::core::policy::Reliability::Reliable()
               << dds::core::policy::Durability::TransientLocal()
               << dds::core::policy::History::KeepAll();
    
    // Create writer
    dds::pub::DataWriter<HelloWorld> writer(publisher, topic, writer_qos);
    
    // Wait for discovery
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    // Publish samples
    for (int i = 1; i <= count; i++) {
        HelloWorld sample;
        sample.message("Hello, World!");
        sample.count(i);
        
        writer.write(sample);
        std::cerr << "Published: count=" << i << std::endl;
        
        if (i < count) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
    }
    
    // Wait for reliable delivery
    std::this_thread::sleep_for(std::chrono::seconds(2));
    
    return 0;
}
```

## CMakeLists.txt

```cmake
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
find_package(RTIConnextDDS REQUIRED)

# Build with pre-generated IDL files (run rtiddsgen before cmake)
add_executable(publisher 
    publisher.cxx 
    HelloWorld.cxx
    HelloWorldPlugin.cxx
)

target_include_directories(publisher PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(publisher RTIConnextDDS::cpp2_api)
```

## Build Instructions

```bash
# Step 1: Generate C++ types from IDL
$NDDSHOME/bin/rtiddsgen -language C++11 -d . HelloWorld.idl

# Step 2: Build with cmake
mkdir build && cd build
cmake .. -DCONNEXTDDS_DIR=$NDDSHOME
make
```

## Key Translation Notes

| Python | C++ |
|--------|-----|
| `dds.DomainParticipant(0)` | `dds::domain::DomainParticipant(0)` |
| `dds.DynamicData.Topic(...)` | `dds::topic::Topic<HelloWorld>(...)` |
| `dds.DataWriterQos()` | `dds::pub::qos::DataWriterQos` |
| `qos.reliability.kind = dds.ReliabilityKind.RELIABLE` | `qos << dds::core::policy::Reliability::Reliable()` |
| `sample["message"] = "Hello"` | `sample.message("Hello")` |
| `time.sleep(2.0)` | `std::this_thread::sleep_for(std::chrono::seconds(2))` |

