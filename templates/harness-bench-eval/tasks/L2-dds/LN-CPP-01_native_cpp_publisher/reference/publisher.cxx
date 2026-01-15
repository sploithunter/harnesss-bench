#include <iostream>
#include <thread>
#include <chrono>
#include <dds/dds.hpp>
#include "HelloWorld.hpp"

int main(int argc, char* argv[]) {
    int count = 10;
    int domain_id = 0;
    
    // Parse command line arguments
    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if ((arg == "--count" || arg == "-c") && i + 1 < argc) {
            count = std::stoi(argv[++i]);
        } else if ((arg == "--domain" || arg == "-d") && i + 1 < argc) {
            domain_id = std::stoi(argv[++i]);
        }
    }
    
    try {
        // Create DomainParticipant
        dds::domain::DomainParticipant participant(domain_id);
        
        // Create Topic with HelloWorld type
        dds::topic::Topic<HelloWorld> topic(participant, "HelloWorld");
        
        // Create Publisher
        dds::pub::Publisher publisher(participant);
        
        // Configure QoS for interoperability
        dds::pub::qos::DataWriterQos writer_qos;
        writer_qos << dds::core::policy::Reliability::Reliable()
                   << dds::core::policy::Durability::TransientLocal()
                   << dds::core::policy::History::KeepAll();
        
        // Create DataWriter
        dds::pub::DataWriter<HelloWorld> writer(publisher, topic, writer_qos);
        
        // Wait for subscriber discovery
        std::cerr << "Waiting for discovery..." << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        // Publish samples
        for (int i = 1; i <= count; i++) {
            HelloWorld sample;
            sample.message("Hello, World!");
            sample.count(i);
            
            writer.write(sample);
            std::cerr << "Published: message=\"Hello, World!\", count=" << i << std::endl;
            
            if (i < count) {
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            }
        }
        
        // Wait for reliable delivery
        std::cerr << "Waiting for delivery..." << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(2));
        
        std::cerr << "Done. Published " << count << " samples." << std::endl;
        
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << std::endl;
        return 1;
    }
    
    return 0;
}
