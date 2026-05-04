#include <Arduino_RouterBridge.h>

String payload = "";     // Our data bucket
String results = "";
bool Receiving = false; // The state flag


void setup() {
  Bridge.begin();
  Monitor.begin();
  payload.reserve(2048); // Allocate Memory
  Bridge.provide_safe("sendRes", sendRes);
}

void sendRes(String Res) {
    Monitor.println(Res); 
}

void loop() {
  if (Monitor.available()) {
      String line = Monitor.readStringUntil('\n');
      line.trim();
      
      if (line == "START"){
        payload = "";
        Receiving = true;
      }
      
      else if (line == "EOF"){
        Receiving = false;
        Bridge.notify("ProcessSamples", payload.c_str());
        payload = "";

      }
        
      else if (Receiving) {
        // Append the line and a newline separator
        if (payload.length() > 0) {
        payload += ","; // Add a comma separator between lines
        }
        
        payload += line;
      }

  }
 
}