# An embedded EMG signal acquisition device for real-time gesture recognition


This project provides a scalable 8-channel Electromyography (EMG) acquisition system designed for the **Arduino UNO Q**. It integrates a custom **ADS1298 Analog Front-End (AFE)** shield with the software to capture biopotentials and perform real-time gesture recognition using on-device Neural Networks This repository contains the software used during testing to both run inferances on the UNO Q and to retrieve data from it. 


## 1. The Model Testbench Program
The Testbench validates the Arduino UNO Q’s ability to execute local neural networks and measures performance metrics such as accuracy and latency.

### Components
* **Prediction Dashboard (Desktop):** A Python-based GUI (Tkinter/Matplotlib) for loading CSV datasets, selecting signal windows, and visualizing confusion matrices and inference times
* **MCU Middleman (C++):** Runs on the STM32; manages serial data flow between the Desktop and the Qualcomm processor via the **Arduino Router Bridge** .
* **MPU Model Runner (Python):** Runs on the Qualcomm QRB2210; handles data windowing (100ms segments), executes the CNN, and calls an RPC function to return the results through the arduino's monitor object.

### Usage
1. Connect the UNO Q via USB-C.
2. Upload the MCU and MPU programs using the arduino app lab and install their dependencies.
3. Ensure both MCU and MPU programs are running via the app lab GUI.
4. Launch the `Dashboard.py` application.
5. Load a gesture dataset (e.g., LibEMG format).
6. Select a data segment and click **"Send Selection"** to trigger remote inference.



## 2. The Data Acquisition (DAQ) Program
The DAQ program enables continuous streaming of raw EMG data from the ADS1298 custom PCB to a host PC for real-time visualization and logging.
This program does not interface with the MPU and therefore only uses a C++ arduino sketch and a PC python program to visualise the signals.

### Software Pipeline
1. **AFE Interfacing:** Polled via the `DRDY` (Data Ready) pin; retrieves 27-byte blocks over SPI.
2. **Double Buffering:** Implemented via **Zephyr RTOS** threads. While one 100-sample buffer fills, a separate thread sends the previous buffer to the PC to prevent data loss.
3. **Visualizer (Desktop):** A Python application that reconstructs 24-bit values from 8-bit encodings and displays them on a live-refreshing plot.

### Componants
1. **Firmware (C++):** A program running on the UNO's STM32 to interface, boot, configure and retrieve data from the ADS1298.
2. **Visualizer** A Desktop Python application to plot the incoming serial EMG data and its frequency information and export it to a CSV file.

### Usage
1. Connect the UNO Q via USB-C.
2. Upload the MCU programs using the arduino app lab or arduino IDE.
3. configure the `Visualizer.py` code's serial port and baud rate. 
4. Launch the `Visualizer.py` application.
5. Export the Data to a CSV using Keys R to record and S to stop.

### Libraries
The python scripts use the following libraries:
1. [NumPY](https://github.com/numpy/numpy)
2. [matplotlib](https://github.com/matplotlib/matplotlib)
3. [Tkinter](https://docs.python.org/3/library/tkinter.html)
4. [pyserial](https://github.com/pyserial/pyserial)
5. [pandas](https://github.com/pandas-dev/pandas).

The DAQ firware uses code adapted version of ADS129x Arduino library by [ferdinandkeil](https://github.com/ferdinandkeil/ADS129X) which itself was originaly adapted from [conorrussomanno](https://github.com/conorrussomanno/ADS1299). This codebase was adapted into the main MCU sketch as the arduino app lab had no dynamic ability to use external libraries at the time of development.

### Datasets
The training data used in the Edge Impulse model training and to test it is the DS11: minimal dataset which can be found in [LibEMG](https://github.com/LibEMG/libemg).



