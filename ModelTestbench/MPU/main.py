import numpy as np
import os
import stat
import json
import time
from datetime import datetime
from edge_impulse_linux.runner import ImpulseRunner
from arduino.app_utils import *

MODEL_PATH = "Models/emg_classifier_1.eim"

if os.path.exists(MODEL_PATH): # set permission to access the eim binary
    st = os.stat(MODEL_PATH)
    os.chmod(MODEL_PATH, st.st_mode | stat.S_IEXEC)
else:
    print(f" Model file not found at {MODEL_PATH}")
    exit(1)

# Setup the EMG model 
runner = ImpulseRunner(MODEL_PATH, timeout=10)
model_info = runner.init()
print(model_info)

def ProcessSamples(full_data_string):

    
    try:    
       
        
        # 1. FASTER PARSING: Avoids the list comprehension loop
        data = np.fromstring(full_data_string, sep=',').reshape(-1, 8)
        
        window_size = 20
        # If your data is exactly 20 rows, this loop runs once.
        for i in range(0, len(data) - window_size + 1, window_size):
            window = data[i : i + window_size].flatten() 
            
            
            start_inference = time.perf_counter()
            res = runner.classify(window) # Only convert at the last second
            end_inference = time.perf_counter()
            
            inference_ms = (end_inference - start_inference) * 1000
            
            if 'result' in res: # format results into a Json 
                packet = {
                    "s": (i // window_size) + 1,
                    "p": res['result']['classification'],
                    "t": round(inference_ms, 2)
                }
                
                json_packet = json.dumps(packet, separators=(',', ':'))
                Bridge.notify("sendRes", json_packet + "\n")
                
            time.sleep(0.02) # a small wait is inefficient but ensures no communication conflicts
        
                  
    except Exception as e:
        print(f"SBC Error: {e}")


def testrun(): # run the model woth an empty list as a sanity check
    features = [0] * 160
    result = runner.classify(features)
    print(result['result']['classification'])
    
    
if __name__ == "__main__":
    Bridge.provide("ProcessSamples", ProcessSamples) #setup process samples as a RPC function
    testrun()
    App.run()
