/*
 * HelloWorld C++ Publisher
 * 
 * Reference implementation for Python-to-C++ translation task.
 * Uses RTI Connext DDS Modern C++ API.
 */

#include <iostream>
#include <thread>
#include <chrono>
#include <cstring>

#include <dds/dds.hpp>
#include "HelloWorld.hpp"  // Generated from HelloWorld.idl

int main(int argc, char* argv[]) {
    int count = 10;
    int domain_id = 0;
    
    // Parse command line arguments
    for (int i = 1; i < argc; i++) {
        if ((strcmp(argv[i], "--count") == 0 || strcmp(argv[i], "-c") == 0) && i + 1 < argc) {
            count = std::stoi(argv[++i]);
        } else if ((strcmp(argv[i], "--domain") == 0 || strcmp(argv[i], "-d") == 0) && i + 1 < argc) {
            domain_id = std::stoi(argv[++i]);
        }
    }
    
    try {
        // Create DomainParticipant
        dds::domain::DomainParticipant participant(domain_id);
        
        // Create Topic
        dds::topic::Topic<HelloWorld> topic(participant, "HelloWorld");
        
        // Create Publisher
        dds::pub::Publisher publisher(participant);
        
        // Create DataWriter with matching QoS
        dds::pub::qos::DataWriterQos writer_qos = 
            dds::core::QosProvider::Default().datawriter_qos();
        
        // Set QoS to match Python subscriber
        writer_qos << dds::core::policy::Reliability::Reliable()
                   << dds::core::policy::Durability::TransientLocal()
                   << dds::core::policy::History::KeepAll();
        
        dds::pub::DataWriter<HelloWorld> writer(publisher, topic, writer_qos);
        
        // Wait for subscriber discovery
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // Publish samples
        HelloWorld sample;
        sample.message("Hello, World!");
        
        for (int i = 1; i <= count; i++) {
            sample.count(i);
            writer.write(sample);
            std::cerr << "Published: count=" << i << std::endl;
            
            if (i < count) {
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            }
        }
        
        // Allow time for reliable delivery
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        std::cerr << "Published " << count << " samples" << std::endl;
        
    } catch (const dds::core::Exception& ex) {
        std::cerr << "DDS Exception: " << ex.what() << std::endl;
        return 1;
    }
    
    return 0;
}


