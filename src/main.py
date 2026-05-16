import cv2
import easyocr
import requests
import re
import os
import csv
import torch
import tkinter as tk
from tkinter import messagebox, scrolledtext
from PIL import Image, ImageTk

# --- GPU check ---
gpu_available = torch.cuda.is_available()
print("CUDA available:", gpu_available)
if gpu_available:
    print("Using device:", torch.cuda.get_device_name(0))
else:
    print("⚠️ CUDA not available, OCR will run on CPU (slower).")

reader = easyocr.Reader(['en', 'pt'], gpu=gpu_available)

def extract_set_and_number(ocr_results):
    collector_number = None
    set_code = None
    confidence = 0.0

    for (_, text, conf) in ocr_results:
        cleaned = text.strip().upper()

        # Match collector number (digits, with optional leading letter)
        if re.match(r"^[A-Z]?\s*\d{1,4}$", cleaned):
            collector_number = re.sub(r"\D", "", cleaned)
            confidence = max(confidence, conf)

        # Match set code (3-4 letters/numbers)
        elif re.match(r"^[A-Z0-9]{3,4}$", cleaned):
            set_code = cleaned.lower()
            confidence = max(confidence, conf)

    return set_code, collector_number, confidence

def query_scryfall(set_code, collector_number):
    url = f"https://api.scryfall.com/cards/search?q=set:{set_code}+cn:{collector_number}"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        if data.get("data"):
            return data["data"][0]
    return None

def save_to_csv(collection):
    os.makedirs("output", exist_ok=True)
    filepath = os.path.join("output", "cardlist.csv")
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Card Name", "Set Code", "Collector Number", "Foil", "OCR Confidence"])
        writer.writerows(collection)
    messagebox.showinfo("Saved", f"Collection saved to {filepath}")

class MTGScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MTG Collection Scanner")

        self.foil_mode = tk.BooleanVar(value=False)
        self.collection = []

        # Camera setup
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Layout frames
        top_frame = tk.Frame(root)
        top_frame.pack(side="top", pady=10)

        bottom_frame = tk.Frame(root)
        bottom_frame.pack(side="top", fill="x", pady=10)

        # Camera preview (resized)
        self.camera_label = tk.Label(top_frame)
        self.camera_label.pack()

        # Controls
        tk.Checkbutton(bottom_frame, text="Foil Mode", variable=self.foil_mode).pack(anchor="w")
        tk.Button(bottom_frame, text="Quit & Save", command=self.quit_app).pack(pady=5)

        self.result_label = tk.Label(bottom_frame, text="No card scanned yet.")
        self.result_label.pack(pady=10)

        self.text_area = scrolledtext.ScrolledText(bottom_frame, width=60, height=15)
        self.text_area.pack(pady=10)

        # Bind keys
        self.root.bind("<space>", lambda event: self.scan_card())
        self.root.bind("<BackSpace>", lambda event: self.delete_last_entry())

        # Start updating camera feed
        self.update_frame()

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame)

            # Resize preview to manageable size
            img = img.resize((480, 270))

            imgtk = ImageTk.PhotoImage(image=img)
            self.camera_label.imgtk = imgtk
            self.camera_label.configure(image=imgtk)
        self.root.after(20, self.update_frame)

    def scan_card(self):
        ret, frame = self.cap.read()
        if not ret:
            messagebox.showerror("Error", "Failed to grab frame from webcam.")
            return

        results = reader.readtext(frame)
        set_code, collector_number, confidence = extract_set_and_number(results)

        if not set_code or not collector_number:
            self.result_label.config(text="Could not detect set/number. Enter manually.")
            return

        card_data = query_scryfall(set_code, collector_number)
        if card_data:
            card_entry = [card_data['name'], card_data['set'].upper(), collector_number,
                          "Foil" if self.foil_mode.get() else "Non-Foil",
                          f"{confidence:.2f}"]

            if confidence >= 0.90:
                # Auto-add if confidence is high
                self.collection.append(card_entry)
                self.text_area.insert(tk.END, f"{card_entry}\n")
                self.result_label.config(
                    text=f"Auto-added: {card_entry[0]} [{card_entry[1]}] | CN: {collector_number} | OCR confidence: {confidence:.2f}"
                )
            else:
                # Ask for confirmation if confidence is low
                confirm = messagebox.askyesno(
                    "Confirm Card",
                    f"Found card: {card_entry[0]} [{card_entry[1]}]\nCollector Number: {collector_number}\nOCR confidence: {confidence:.2f}\n\nAdd to list?"
                )
                if confirm:
                    self.collection.append(card_entry)
                    self.text_area.insert(tk.END, f"{card_entry}\n")
                    self.result_label.config(text="Card confirmed and added.")
                else:
                    self.result_label.config(text="Card not added.")
        else:
            self.result_label.config(text="Card not found in Scryfall.")

    def delete_last_entry(self):
        if self.collection:
            removed = self.collection.pop()
            # Clear and redraw text area
            self.text_area.delete("1.0", tk.END)
            for entry in self.collection:
                self.text_area.insert(tk.END, f"{entry}\n")
            self.result_label.config(text=f"Removed last entry: {removed[0]} [{removed[1]}] CN: {removed[2]}")
        else:
            self.result_label.config(text="No entries to remove.")

    def quit_app(self):
        self.cap.release()
        cv2.destroyAllWindows()
        if self.collection:
            save_to_csv(self.collection)
        self.root.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = MTGScannerApp(root)
    root.mainloop()
