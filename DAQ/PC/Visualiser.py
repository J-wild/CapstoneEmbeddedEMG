import serial
import time
import threading
import numpy as np
from collections import deque
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec
import csv
from datetime import datetime
import queue

#  CONFIGURATION 
PORT             = "COM6"
BAUD             = 115200
BYTES_PER_SAMPLE = 27
CHANNELS         = 8
WINDOW_SAMPLES   = 1000
VREF             = 2.4
GAIN             = 12.0
MAX_VAL          = 8388608.0
UPDATE_MS        = 50
SAMPLE_RATE_HZ   = 250

# FFT CONFIGURATION 
FFT_SAMPLES   = 512
FFT_FREQS     = np.fft.rfftfreq(FFT_SAMPLES, d=1.0 / SAMPLE_RATE_HZ)
FFT_MAX_HZ    = 125
FFT_FREQ_MASK = FFT_FREQS <= FFT_MAX_HZ      
FFT_WINDOW    = np.hanning(FFT_SAMPLES)

# SHARED STATE
channel_buffers = [deque([0.0] * WINDOW_SAMPLES, maxlen=WINDOW_SAMPLES) for _ in range(CHANNELS)]
byte_buffer = bytearray()
lock = threading.Lock()
csv_queue = queue.Queue()

current_sps = 0.0
total_samples_parsed = 0
is_recording = False
current_filename = ""

# SERIAL THREAD 
def serial_reader():
    global byte_buffer, current_sps, total_samples_parsed
    rolling_samples = 0
    window_start_t = time.time()
    rolling_window_len = 2.0

    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.1) #start the serial connection
        ser.flushInput()

    except Exception as e:
        print(f"Serial Error: {e}")
        return

    while True:
        chunk = ser.read(2048)  #read incoming data in batches
        if not chunk: continue
        with lock:
            byte_buffer.extend(chunk)
            while len(byte_buffer) >= BYTES_PER_SAMPLE:         #when there is enough data to constitute a sample 
                if (byte_buffer[0] & 0xF0) != 0xC0:              #check for the header byte to sync
                    del byte_buffer[0]
                    continue
                sample = byte_buffer[:BYTES_PER_SAMPLE]
                channels_mv = []
            
                for ch in range(CHANNELS):                          # read each channel at the index 'start' and convert into mV
                    start = 3 + (ch * 3)
                    raw = int.from_bytes(sample[start:start + 3], byteorder='big', signed=True)
                    val = (raw * VREF) / (GAIN * MAX_VAL) * 1000.0
                    channels_mv.append(val)
                    channel_buffers[ch].append(val)

                if is_recording:                                    # if the system is set to record put the data to the csv file
                    rel_t = total_samples_parsed / SAMPLE_RATE_HZ
                    wall = datetime.now().strftime("%H:%M:%S.%f")
                    csv_queue.put((current_filename, [rel_t, wall, total_samples_parsed] + channels_mv))

                del byte_buffer[:BYTES_PER_SAMPLE]
                total_samples_parsed += 1
                rolling_samples += 1
            now = time.time()

            elapsed = now - window_start_t
            if elapsed >= rolling_window_len:   #calculate the incoming samples per seco
                current_sps = rolling_samples / elapsed
                rolling_samples = 0
                window_start_t = now

def csv_handler():
    file_handle = None
    writer = None
    last_filename = None
    flush_counter = 0
    while is_recording or not csv_queue.empty():
        try:
            filename, row = csv_queue.get(timeout=0.5) # write to the CSV when data appears on its queue 
            if filename != last_filename:
                if file_handle: file_handle.close()
                file_handle = open(filename, 'a', newline='')
                writer = csv.writer(file_handle)
                last_filename = filename
            writer.writerow(row)

            flush_counter += 1
            if flush_counter >= 50: # flush the data to the file every 50 samples incase the program crashes
                file_handle.flush()
                flush_counter = 0
        except queue.Empty: continue

    if file_handle:
        file_handle.flush()
        file_handle.close()

def compute_fft(data):
    segment  = data[-FFT_SAMPLES:] # for however many samples there are
    windowed = segment * FFT_WINDOW
    spectrum = np.fft.rfft(windowed) # create an FFT spectrum
    magnitude = (2.0 / FFT_SAMPLES) * np.abs(spectrum)
    return magnitude[FFT_FREQ_MASK] # return the magnitude 

# PLOT SETUP 
plt.rcParams.update({'font.size': 12})  # formatted as close to IEEE standard as is reasonable
plt.rcParams['font.family'] = 'sans-serif'
fig = plt.figure(figsize=(20, 12), facecolor="white") 

gs = GridSpec(
    9, 2,
    figure=fig,
    hspace=0.6,
    wspace=0.12, 
    bottom=0.07, top=0.92,
    left=0.08,  right=0.95,
    width_ratios=[2.5, 1]
)

time_axes, fft_axes = [], []
time_lines, fft_lines = [], []
fft_peak_texts = [] # To store the spike value labels

x_vec = np.arange(WINDOW_SAMPLES)
fft_x = FFT_FREQS[FFT_FREQ_MASK]
fft_zeros = np.zeros(fft_x.size)

# The initial creation of each graph

for i in range(CHANNELS):
    # Time-domain axis
    tax = fig.add_subplot(gs[i, 0])
    tline, = tax.plot(x_vec, np.zeros(WINDOW_SAMPLES), color='black', linewidth=1.0)
    tax.set_xlim(0, WINDOW_SAMPLES)
    tax.set_ylabel(f"CH{i+1}", fontsize=14, fontweight='bold', rotation=0, labelpad=25, va='center')
    tax.tick_params(labelsize=11)
    if i < CHANNELS - 1: tax.set_xticklabels([])
    else: tax.set_xlabel("Samples", fontsize=14)
    time_axes.append(tax)
    time_lines.append(tline)

    # FFT axis
    fax = fig.add_subplot(gs[i, 1])
    fline, = fax.plot(fft_x, fft_zeros, color='crimson', linewidth=1.2)
    fax.set_xlim(0, FFT_MAX_HZ)
    fax.set_ylim(0, 0.1)
    fax.tick_params(labelsize=11)

    # Peak value text overlay
    ptext = fax.text(0.95, 0.75, "", transform=fax.transAxes, 
                     fontsize=11, fontweight='bold', ha='right', color='darkred')
    if i < CHANNELS - 1: fax.set_xticklabels([])
    else: fax.set_xlabel("Hz", fontsize=14)
    fft_axes.append(fax)
    fft_lines.append(fline)
    fft_peak_texts.append(ptext)

time_axes[0].set_title("TIME DOMAIN (mV)", fontsize=16, pad=10, fontweight='bold')
fft_axes[0].set_title("FFT SPECTRUM", fontsize=16, pad=10, fontweight='bold')

info_ax = fig.add_subplot(gs[8, :])
info_ax.axis("off")
debug_text = info_ax.text(0.5, 0, "R: Record | S: Stop", 
                          transform=info_ax.transAxes, fontsize=12, ha='center', fontweight='bold')

# ANIMATION
def update(frame):
    with lock:
        sps = current_sps
        total = total_samples_parsed
        snapshots = [np.array(buf) for buf in channel_buffers]

    for i in range(CHANNELS):
        data = snapshots[i]
        time_lines[i].set_ydata(data)
        
        # Auto-scale Time Domain
        if frame % 10 == 0:
            ymin, ymax = data.min(), data.max()
            pad = max((ymax - ymin) * 0.2, 0.1)
            time_axes[i].set_ylim(ymin - pad, ymax + pad)

        # FFT Update
        mag = compute_fft(data)
        fft_lines[i].set_ydata(mag)

        # Calculate Spike Value
        peak_idx = np.argmax(mag)
        peak_val = mag[peak_idx]
        peak_hz  = fft_x[peak_idx]
        fft_peak_texts[i].set_text(f"{peak_val:.3f} mV @ {peak_hz:.1f}Hz")

        # Auto-scale FFT
        if frame % 10 == 0:
            curr_top = fft_axes[i].get_ylim()[1]
            new_top  = max(peak_val * 1.3, 0.05)
            if peak_val > curr_top or new_top < curr_top * 0.3:
                fft_axes[i].set_ylim(0, new_top)

    status = f"RECORDING: {current_filename}" if is_recording else "STATUS: IDLE"
    debug_text.set_text(f"{status}  |  SPS: {sps:.1f}  |  Total Samples: {total:,}")

    return time_lines + fft_lines + fft_peak_texts + [debug_text]

def on_key(event):
    global is_recording, current_filename
    if event.key == 'r' and not is_recording:
        current_filename = f"EMG_Data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        headers = ["Time", "Clock", "Idx"] + [f"CH{i+1}" for i in range(CHANNELS)]
        with open(current_filename, 'w', newline='') as f:
            csv.writer(f).writerow(headers)
        is_recording = True
        threading.Thread(target=csv_handler, daemon=True).start()
    if event.key == 's':
        is_recording = False

fig.canvas.mpl_connect('key_press_event', on_key)
threading.Thread(target=serial_reader, daemon=True).start()
ani = animation.FuncAnimation(fig, update, interval=UPDATE_MS, blit=True)
plt.show()