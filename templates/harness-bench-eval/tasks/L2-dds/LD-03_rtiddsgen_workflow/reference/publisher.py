#!/usr/bin/env python3
"""Publisher using rtiddsgen-generated types."""

import time
import rti.connextdds as dds
from HelloWorld import HelloWorld  # Generated type

def main():
    participant = dds.DomainParticipant(0)
    
    # Use generated type directly
    topic = dds.Topic(participant, "HelloWorld", HelloWorld)
    
    publisher = dds.Publisher(participant)
    writer = dds.DataWriter(publisher, topic)
    
    time.sleep(2.0)  # Discovery
    
    for i in range(1, 11):
        sample = HelloWorld()
        sample.message = f"Hello World {i}"
        sample.count = i
        writer.write(sample)
        time.sleep(0.5)
    
    time.sleep(1.0)
    print(f"Published 10 samples")

if __name__ == "__main__":
    main()
