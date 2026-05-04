import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
import pandas as pd
import matplotlib.pyplot as pltfrom matplotlib.widgets import SpanSelector
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import serial  
import time
import threading
import json
from datetime import datetime
import numpy as np

CLR_BG = "#f8f9fa"       
CLR_SIDEBAR = "#ffffff"  
CLR_ACCENT = "#4a90e2"   
CLR_SUCCESS = "#28a745"  
CLR_TEXT = "#333333"     

class DashboardAPP:
    def __init__(self, root):
        self.root = root
        self.root.title("Prediction Dashboard")
        self.root.geometry("1400x900")
        self.root.configure(bg=CLR_BG)

        # --- State Variables ---
        self.ser = None
        self.listen_for_results = False
        self.current_selection = None
        self.df = None
        self.span = None
        self.start_time = 0
        self.current_batch_id = "None"
        
        # --- Configurable Defaults ---
        self.history = [] 
        # Default gestures
        default_gestures = ["Closed", "Open", "No Motion", "Wrist Extension", "Wrist Flexion"]
        self.gesture_map = {str(i): name for i, name in enumerate(default_gestures)}
        self.target_gesture = tk.StringVar(value="0")
        
        self.expected_packets = 0
        self.received_count = 0
        self.last_total_rtt = 0

        self.create_layout()
        self.update_gesture_ui_list() # Build initial radio buttons
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        style = ttk.Style()
        style.theme_use('default')
        style.configure("TNotebook", background=CLR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#dee2e6", padding=[10, 5], font=('Helvetica', 9))
        style.map("TNotebook.Tab", background=[("selected", CLR_ACCENT)], foreground=[("selected", "white")])

    def create_layout(self):
        # TOP HEADER
        self.header = tk.Frame(self.root, bg=CLR_SIDEBAR, height=60, bd=0, highlightthickness=1, highlightbackground="#e1e4e8")
        self.header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(self.header, text="Prediction Dashboard", font=("Helvetica", 14, "bold"), bg=CLR_SIDEBAR, fg=CLR_ACCENT).pack(side=tk.LEFT, padx=20)
        self.status_pill = tk.Label(self.header, text="DISCONNECTED", font=("Helvetica", 8, "bold"), bg="#fee2e2", fg="#ef4444", padx=10, pady=2)
        self.status_pill.pack(side=tk.RIGHT, padx=20)

        # SIDEBAR
        self.sidebar_canvas = tk.Canvas(self.root, bg=CLR_SIDEBAR, width=320, bd=0, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.root, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar = tk.Frame(self.sidebar_canvas, bg=CLR_SIDEBAR)
        
        self.sidebar_canvas.create_window((0, 0), width = 320, window=self.sidebar, anchor="nw")
        self.sidebar_canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.sidebar_canvas.pack(side=tk.LEFT, fill=tk.Y)
        self.scrollbar.pack(side=tk.LEFT, fill=tk.Y)

        # --- SECTION 0: CONFIGURATION ---
        self.add_sidebar_label("Step 0. Configuration")
        self.chan_entry = self.add_input_field("Number of Channels", "8")
        self.gesture_names_entry = self.add_input_field("Gesture Names (Comma Separated)", "Closed, Open, No Motion, Wrist Extension, Wrist Flexion")
        tk.Button(self.sidebar, text="Apply Settings", bg="#6c757d", fg="white", font=("Helvetica", 9, "bold"), command=self.apply_settings).pack(fill="x", padx=30, pady=5)

        # --- SECTION 1: CONNECTION ---
        self.add_sidebar_label("Step 1. Serial Connection")
        self.port_entry = self.add_input_field("Serial Port", "COM6")
        self.btn_conn = tk.Button(self.sidebar, text="Connect Device", bg=CLR_ACCENT, fg="white", font=("Helvetica", 10, "bold"), relief="flat", command=self.toggle_connection)
        self.btn_conn.pack(fill="x", padx=30, pady=5)

        # --- SECTION 2: DATA ---
        self.add_sidebar_label("Step 2. Select EMG Sample")
        self.rate_entry = self.add_input_field("Sample Rate (Hz)", "200")
        tk.Button(self.sidebar, text="Select File", bg="#6c757d", fg="white", font=("Helvetica", 10, "bold") ,relief="flat", command=self.load_data).pack(fill="x", padx=30, pady=5)

        # --- SECTION 3: GESTURE SELECTION ---
        self.add_sidebar_label("Step 3. Target Gesture")
        self.gesture_frame = tk.Frame(self.sidebar, bg=CLR_SIDEBAR)
        self.gesture_frame.pack(fill="x", pady=5)

        self.btn_send = tk.Button(self.sidebar, text="Send Selection",bg="#6c757d", fg="white", font=("Helvetica", 10, "bold"),  relief="flat",command=self.transmit_data, state="disabled")
        self.btn_send.pack(fill="x", padx=30, pady=5)

        self.btn_send_all = tk.Button(self.sidebar, text="Send Full File", bg="#6c757d", fg="white", font=("Helvetica", 10, "bold"),  relief="flat", command=self.select_and_send_all, state="disabled")
        self.btn_send_all.pack(fill="x", padx=30, pady=(15, 5))

        self.add_sidebar_label("LIVE LOG")
        self.txt_results = scrolledtext.ScrolledText(self.sidebar, height=12, font=("Courier New", 9), bg="#f1f3f5")
        self.txt_results.pack(fill="x", padx=20, pady=5)
        
        tk.Button(self.sidebar, text="Reset Stats", font=("Helvetica", 8), command=self.reset_stats).pack(padx=20, anchor="e")

        self.btn_export = tk.Button(self.sidebar, text="Export Results", bg="#6c757d", fg="white", font=("Helvetica", 10, "bold"), relief="flat", command=self.export_results)
        self.btn_export.pack(fill="x", padx=30, pady=10)

        # MAIN CONTENT AREA
        self.main_area = tk.Frame(self.root, bg=CLR_BG)
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_waveform = tk.Frame(self.notebook, bg=CLR_BG)
        self.notebook.add(self.tab_waveform, text="  Signal Preview  ")

        self.tab_analytics = tk.Frame(self.notebook, bg=CLR_BG)
        self.notebook.add(self.tab_analytics, text="  Debug & Stats  ")

        # Plots
        self.plot_container = tk.Frame(self.tab_waveform, bg="white", highlightthickness=1, highlightbackground="#e1e4e8")
        self.plot_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.fig, self.ax = plt.subplots(figsize=(5, 3), facecolor="white")
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.plot_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.info_bar = tk.Frame(self.tab_waveform, bg=CLR_BG, pady=5)
        self.info_bar.pack(fill=tk.X, padx=15)
        self.lbl_samples = tk.Label(self.info_bar, text="Samples: 0", font=("Helvetica", 9), bg=CLR_BG, fg="#666666")
        self.lbl_samples.pack(side=tk.LEFT, padx=(0, 20))
        self.lbl_time = tk.Label(self.info_bar, text="Duration: 0ms", font=("Helvetica", 9), bg=CLR_BG, fg="#666666")
        self.lbl_time.pack(side=tk.LEFT)

        self.stats_container = tk.Frame(self.tab_analytics, bg="white", highlightthickness=1, highlightbackground="#e1e4e8")
        self.stats_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.fig_stats = plt.Figure(figsize=(10, 7), facecolor="white")
        self.ax_cm = self.fig_stats.add_subplot(221)   
        self.ax_pie = self.fig_stats.add_subplot(222)  
        self.ax_time = self.fig_stats.add_subplot(212) 
        self.stats_canvas = FigureCanvasTkAgg(self.fig_stats, master=self.stats_container)
        self.stats_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Update sidebar scroll region
        self.sidebar.update_idletasks()
        self.sidebar_canvas.config(scrollregion=self.sidebar_canvas.bbox("all"))

    def apply_settings(self):
        """Updates the internal gesture map and channels based on user input."""
        try:
            # Update gestures
            raw_names = self.gesture_names_entry.get().split(",")
            names = [n.strip() for n in raw_names if n.strip()]
            if not names:
                raise ValueError("Must have at least one gesture name.")
            
            self.gesture_map = {str(i): name for i, name in enumerate(names)}
            self.target_gesture.set("0")
            self.update_gesture_ui_list()
            
            # Reset history as the classes have changed
            self.reset_stats()
            messagebox.showinfo("Settings", "Configuration updated successfully!")
        except Exception as e:
            messagebox.showerror("Config Error", f"Invalid input: {e}")

    def update_gesture_ui_list(self):
        """Rebuilds the radio button list in the sidebar."""
        for widget in self.gesture_frame.winfo_children():
            widget.destroy()
        
        for g_id, g_name in self.gesture_map.items():
            tk.Radiobutton(self.gesture_frame, text=f"{g_id}: {g_name}", 
                           variable=self.target_gesture, value=g_id, 
                           bg=CLR_SIDEBAR, font=("Helvetica", 10)).pack(anchor="w", padx=30)
        
        # Update sidebar scrollable area
        self.sidebar.update_idletasks()
        self.sidebar_canvas.config(scrollregion=self.sidebar_canvas.bbox("all"))

    def load_data(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not path: return
        try:
            num_chans = int(self.chan_entry.get())
            self.df = pd.read_csv(path, header=None).iloc[:, :num_chans]
            
            fs = float(self.rate_entry.get())
            time_axis = np.arange(len(self.df)) / fs
            
            self.ax.clear()
            for i in range(num_chans): 
                self.ax.plot(time_axis, self.df.iloc[:, i], lw=0.7, label=f"CH{i}")
                # Adding Labels

            self.ax.set_xlabel("Time (seconds)", fontsize=9, fontweight='bold')
            self.ax.set_ylabel("Amplitude (mV)", fontsize=9, fontweight='bold')
            self.ax.set_title("EMG Signal Preview", fontsize=10)
            
            self.ax.legend(loc='upper right', fontsize=8)
            

            self.ax.grid(True, alpha=0.3)
            self.span = SpanSelector(self.ax, self.onselect, 'horizontal', useblit=True, props=dict(alpha=0.3, facecolor='gold'))
            self.canvas.draw()
            self.btn_send_all.config(state="normal")
            self.btn_send.config(state="normal")
        except Exception as e: 
            messagebox.showerror("Error", f"Could not load data. Check channel settings.\n{e}")

  

    def onselect(self, xmin, xmax):
        try:
            fs = float(self.rate_entry.get())
            start_idx, end_idx = int(xmin * fs), int(xmax * fs)
            self.current_selection = self.df.iloc[start_idx:end_idx, :]
            self.lbl_samples.config(text=f"Samples: {len(self.current_selection):,}")
            self.lbl_time.config(text=f"Duration: {(len(self.current_selection)/fs)*1000:.1f}ms")
        except: pass

    def select_and_send_all(self):
        if self.df is not None:
            self.current_selection = self.df
            self.transmit_data()

    def update_prediction_ui(self, item):
        try:
            preds = item.get('p', {})
            inf_time = item.get('t', 0)
            actual_id = self.target_gesture.get()
            if preds:
                self.received_count += 1
                winner_id = str(max(preds, key=preds.get))
                self.history.append({
                    'batch_id': self.current_batch_id,
                    'actual': actual_id, 
                    'predicted': winner_id, 
                    'inf_time_ms': inf_time,
                    'all_probs': preds,
                    'batch_rtt_ms': 0  
                })
                is_correct = "✓" if winner_id == actual_id else "✗"
                self.txt_results.insert(tk.END, f"[{self.received_count:0>2}] Pred: {winner_id} {is_correct} | {inf_time}ms\n")
                self.txt_results.see(tk.END)
                if self.received_count >= self.expected_packets and self.expected_packets > 0:
                    total_rtt = (time.perf_counter() - self.start_time) * 1000
                    self.last_total_rtt = total_rtt
                    for entry in reversed(self.history):
                        if entry['batch_id'] == self.current_batch_id: entry['batch_rtt_ms'] = round(total_rtt, 2)
                        else: break 
                    self.txt_results.insert(tk.END, f"BATCH COMPLETE - RTT: {total_rtt:.2f}ms\n{'-'*30}\n")
                    self.expected_packets = 0 
                    self.update_stats_plots(batch_complete=True)
                else: self.update_stats_plots(batch_complete=False)
        except Exception as e: print(f"UI Update Error: {e}")

    def toggle_connection(self):
        if self.ser is None or not self.ser.is_open:
            try:
                self.ser = serial.Serial(self.port_entry.get(), 115200, timeout=0.1)
                self.listen_for_results = True
                threading.Thread(target=self.serial_listener_thread, daemon=True).start()
                self.status_pill.config(text="CONNECTED", bg="#d1fae5", fg="#059669")
                self.btn_conn.config(text="Disconnect", bg="#ef4444")
                self.btn_send.config(state="normal")
            except Exception as e: messagebox.showerror("Error", str(e))
        else: self.disconnect_serial()

    def disconnect_serial(self):
        self.listen_for_results = False
        if self.ser: self.ser.close()
        self.ser = None
        self.status_pill.config(text="DISCONNECTED", bg="#fee2e2", fg="#ef4444")
        self.btn_conn.config(text="Connect Device", bg=CLR_ACCENT)

    def serial_listener_thread(self):
        buffer = ""
        while self.listen_for_results:
            try:
                if self.ser and self.ser.in_waiting > 0:
                    buffer += self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                    if "\n" in buffer:
                        parts = buffer.split("\n")
                        for msg in parts[:-1]:
                            if msg.strip():
                                try:
                                    data = json.loads(msg)
                                    self.root.after(0, self.update_prediction_ui, data)
                                except: pass
                        buffer = parts[-1]
                else: time.sleep(0.001)
            except: break

    def transmit_data(self):
        if self.current_selection is not None and self.ser:
            self.current_batch_id = time.strftime("%Y%m%d_%H%M%S")
            self.notebook.select(1)
            self.expected_packets = len(self.current_selection) // 20
            self.received_count = 0
            self.start_time = time.perf_counter() 
            
            self.ser.write(b"START\n")
            for line in self.current_selection.to_csv(index=False, header=False).splitlines():
                self.ser.write((line + "\n").encode())
                time.sleep(0.002)
            self.ser.write(b"EOF\n")

    def _process_plot_data_worker(self, batch_complete):
        try:
            num_classes = len(self.gesture_map)
            matrix = np.zeros((num_classes, num_classes))
            for entry in self.history:
                try:
                    act = int(entry['actual'])
                    pre = int(entry['predicted'])
                    if act < num_classes and pre < num_classes:
                        matrix[act][pre] += 1
                except: continue

            times = [h['inf_time_ms'] for h in self.history[-50:]] if self.history else []
            pie_data = None
            if batch_complete and self.received_count > 0:
                recent_batch = self.history[-self.received_count:]
                total_compute = sum([h['inf_time_ms'] for h in recent_batch])
                overhead = max(0, self.last_total_rtt - total_compute)
                pie_data = [total_compute, overhead]

            self.root.after(0, self._render_plots_callback, matrix, times, pie_data)
        except Exception as e: print(f"Plot processing error: {e}")

    def _render_plots_callback(self, matrix, times, pie_data):
        try:
            self.ax_cm.clear()
            self.ax_cm.imshow(matrix, interpolation='nearest', cmap='Blues')
            self.ax_cm.set_title("Confusion Matrix", fontsize=9, fontweight='bold')
            # Add tick labels for gestures
            ticks = np.arange(len(self.gesture_map))
            self.ax_cm.set_xticks(ticks)
            self.ax_cm.set_yticks(ticks)
            self.ax_cm.set_xticklabels(list(self.gesture_map.keys()), fontsize=7)
            self.ax_cm.set_yticklabels(list(self.gesture_map.values()), fontsize=7)

            self.ax_time.clear()
            if times:
                self.ax_time.plot(times, color=CLR_ACCENT, marker='o', markersize=2)
                self.ax_time.set_title("Inference Latency (ms)", fontsize=9)
                self.ax_time.grid(True, alpha=0.3)

            if pie_data:
                self.ax_pie.clear()
                self.ax_pie.pie(pie_data, labels=['SBC', 'System'], autopct='%1.1f%%', startangle=140, colors=[CLR_SUCCESS, '#ffc107'])
                self.ax_pie.set_title("Latency Breakdown", fontsize=9)

            self.fig_stats.tight_layout()
            self.stats_canvas.draw_idle()
        except Exception as e: print(f"Plot rendering error: {e}")

    def update_stats_plots(self, batch_complete=False):
        threading.Thread(target=self._process_plot_data_worker, args=(batch_complete,), daemon=True).start()

    def export_results(self):
        if not self.history:
            messagebox.showwarning("No Data", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if not path: return
        try:
            df_final = pd.DataFrame(self.history)
            probs_df = pd.json_normalize(df_final['all_probs']).add_prefix('prob_')
            df_final = pd.concat([df_final.drop(columns=['all_probs']), probs_df], axis=1)
            df_final['actual_name'] = df_final['actual'].map(self.gesture_map)
            df_final['predicted_name'] = df_final['predicted'].map(self.gesture_map)
            df_final.to_csv(path, index=False)
            messagebox.showinfo("Success", f"Exported {df_final['batch_id'].nunique()} batches.")
        except Exception as e: messagebox.showerror("Error", str(e))

    def add_sidebar_label(self, title):
        tk.Label(self.sidebar, text=title, font=("Helvetica", 8, "bold"), bg=CLR_SIDEBAR, fg="#999999").pack(anchor="w", padx=30, pady=(15, 5))

    def add_input_field(self, label_text, default_val):
        tk.Label(self.sidebar, text=label_text, font=("Helvetica", 9), bg=CLR_SIDEBAR).pack(anchor="w", padx=30)
        ent = tk.Entry(self.sidebar, highlightthickness=1)
        ent.insert(0, default_val)
        ent.pack(fill="x", padx=30, pady=(0, 5))
        return ent

    def reset_stats(self):
        self.history = []
        self.txt_results.delete('1.0', tk.END)
        self.update_stats_plots()

    def on_closing(self):   
        self.disconnect_serial()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DashboardAPP(root)
    root.mainloop()