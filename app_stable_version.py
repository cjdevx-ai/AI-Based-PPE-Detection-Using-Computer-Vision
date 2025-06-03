import cv2
from pyzbar import pyzbar
import pyperclip
import datetime
import firebase_admin
from firebase_admin import credentials, db
from kivy.app import App
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.screenmanager import ScreenManager, Screen
import os
from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw, ImageFont
import threading
import time

# --- Camera Indexes ---
qr_cam_index = 1
ppe_cam_index = 0

# --- Firebase Initialization ---
cred = credentials.Certificate("ode-project-734d6-firebase-adminsdk-fbsvc-619b1a34a2.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ode-project-734d6-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })

ref = db.reference('/')
front_ref = db.reference('/front')
qr_data_ref = db.reference('DWS-In-Out/')

def write_user_data_to_firebase(id_number, timestamp):
    users_ref = qr_data_ref.child(timestamp)
    users_ref.set({'ID Number': id_number})
    print("✅ Data successfully written to Firebase")

# --- Screens ---
class IdleScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        layout = BoxLayout(orientation='vertical')
        label = Label(text="Welcome to SmartGate", font_size=40)
        layout.add_widget(label)
        self.add_widget(layout)
        # Start polling for 'front' value again
        threading.Thread(target=self.poll_firebase_for_front, daemon=True).start()

    def poll_firebase_for_front(self):
        while True:
            try:
                front_value = front_ref.get()
                if front_value == 1:
                    print("🔑 Front = 1 detected. Proceeding to QR scan.")
                    Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'countdown'))
                    break
            except Exception as e:
                print(f"Error polling Firebase: {e}")
            time.sleep(1)

class CountdownScreen(Screen):
    def on_enter(self):
        self.count = 5
        self.clear_widgets()
        self.layout = BoxLayout(orientation='vertical')
        self.label = Label(text=f"Scanning QR in {self.count}", font_size=100)
        self.layout.add_widget(self.label)
        self.add_widget(self.layout)
        self.event = Clock.schedule_interval(self.update_countdown, 1)

    def update_countdown(self, dt):
        self.count -= 1
        if self.count >= 0:
            self.label.text = f"Scanning QR in {self.count}"
        else:
            Clock.unschedule(self.event)
            self.manager.current = 'camera'

class CameraScreen(Screen):
    def on_enter(self):
        self.capture = cv2.VideoCapture(qr_cam_index)
        self.image_widget = KivyImage()
        self.add_widget(self.image_widget)
        self.scanned_data = set()
        self.event = Clock.schedule_interval(self.update, 1.0 / 30.0)

    def update(self, dt):
        ret, frame = self.capture.read()
        if not ret:
            return
        frame = cv2.flip(frame, 0)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        barcodes = pyzbar.decode(frame)
        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
            if barcode_data not in self.scanned_data:
                self.scanned_data.add(barcode_data)
                pyperclip.copy(barcode_data)
                now = datetime.datetime.now()
                formatted_datetime = now.strftime("%Y-%m-%d %H:%M:%S")
                write_user_data_to_firebase(barcode_data, formatted_datetime)
                self.manager.get_screen('authorized_access').current_timestamp = formatted_datetime
                Clock.unschedule(self.event)
                print(f"📥 Scanned and uploaded: {barcode_data}")
                self.capture.release()
                self.manager.current = 'authorized_access'
        buf = frame_rgb.tobytes()
        texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='rgb')
        texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
        self.image_widget.texture = texture

    def on_leave(self):
        if hasattr(self, 'event'):
            Clock.unschedule(self.event)
        if hasattr(self, 'capture'):
            self.capture.release()
        self.clear_widgets()

class AuthorizedAccessScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_timestamp = None

    def on_enter(self):
        self.count = 10
        self.clear_widgets()
        self.layout = BoxLayout(orientation='vertical')
        self.image_widget = KivyImage()
        self.layout.add_widget(self.image_widget)
        self.label = Label(text=f"Authorized Access\nScanning PPE in {self.count}", font_size=20)
        self.layout.add_widget(self.label)
        self.add_widget(self.layout)
        self.ppe_capture = cv2.VideoCapture(ppe_cam_index)
        self.ppe_event = Clock.schedule_interval(self.update_ppe, 1.0 / 30.0)
        self.event = Clock.schedule_interval(self.update_countdown, 1)

    def update_countdown(self, dt):
        self.count -= 1
        if self.count >= 0:
            self.label.text = f"Scanning PPE in {self.count}"
        else:
            Clock.unschedule(self.event)
            self.capture_ppe_image_and_infer()

    def capture_ppe_image_and_infer(self):
        ret, frame = self.ppe_capture.read()
        if not ret:
            print("❌ Failed to capture image from PPE camera")
            self.label.text = "❌ Failed to capture image. Retrying..."
            self.restart_countdown()
            return
        rotated_frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        image_path = "ppe_capture.jpg"
        cv2.imwrite(image_path, rotated_frame)
        self.run_roboflow_inference(image_path)

    def run_roboflow_inference(self, image_path):
        image = Image.open(image_path).convert("RGB")
        CLIENT = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key="ipRXafHM2fxthdHpXUSC"
        )
        try:
            result = CLIENT.infer(image_path, model_id="ppe-ukjvg/3")
        except Exception as e:
            print(f"❌ Inference error: {e}")
            self.label.text = "❌ Inference failed. Retrying..."
            os.remove(image_path)
            self.restart_countdown()
            return
        draw = ImageDraw.Draw(image, "RGBA")
        class_colors = {
            "hardhat": (255, 255, 0, 200),
            "vest": (128, 0, 128, 200),
            "gloves": (255, 0, 0, 200),
            "shoes": (0, 255, 255, 200),
        }
        try:
            font = ImageFont.truetype("arial.ttf", 25)
        except:
            font = ImageFont.load_default()
        detected_items = set()
        for pred in result["predictions"]:
            label = pred["class"]
            confidence = pred["confidence"]
            if confidence > 0.5:
                detected_items.add(label)
            x0 = pred["x"] - pred["width"] / 2
            y0 = pred["y"] - pred["height"] / 2
            x1 = x0 + pred["width"]
            y1 = y0 + pred["height"]
            label_text = f"{label} ({confidence:.2f})"
            color = class_colors.get(label, (255, 255, 255, 200))
            for offset in range(5):
                draw.rectangle([x0 - offset, y0 - offset, x1 + offset, y1 + offset], outline=color[:3])
            text_bbox = draw.textbbox((x0, y0), label_text, font=font)
            text_x0, text_y0, text_x1, text_y1 = text_bbox
            text_height = text_y1 - text_y0
            text_width = text_x1 - text_x0
            draw.rectangle([x0, y0 - text_height - 10, x0 + text_width + 10, y0], fill=color)
            draw.text((x0 + 5, y0 - text_height - 5), label_text, fill=(255, 255, 255), font=font)
        annotated_path = "annotated_ppe_result.jpg"
        image.save(annotated_path)
        print(f"💾 Annotated image saved at: {annotated_path}")
        hardhat = 1 if "hardhat" in detected_items else 0
        vest = 1 if "vest" in detected_items else 0
        gloves = 1 if "gloves" in detected_items else 0
        if self.current_timestamp:
            ppe_ref = qr_data_ref.child(self.current_timestamp)
            ppe_ref.update({
                "hardhat": hardhat,
                "vest": vest,
                "gloves": gloves
            })
            print(f"📝 PPE data updated in Firebase under {self.current_timestamp}")
        if hardhat and vest and gloves:
            print("✅ Access Granted: Complete PPE Detected")
            self.label.text = "✅ Access Granted: Complete PPE Detected"
            Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'ppe_image'), 2)
        else:
            print("❌ Access Denied: Incomplete PPE. Retrying scan...")
            self.label.text = "Incomplete PPE detected. Retrying..."
            Clock.schedule_once(lambda dt: self.restart_countdown(), 5)
        os.remove(image_path)

    def restart_countdown(self):
        self.count = 10
        self.event = Clock.schedule_interval(self.update_countdown, 1)

    def update_ppe(self, dt):
        ret, frame = self.ppe_capture.read()
        if not ret:
            return
        frame = cv2.flip(frame, 0)
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        buf = frame_rgb.tobytes()
        texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='rgb')
        texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
        self.image_widget.texture = texture

    def on_leave(self):
        if hasattr(self, 'ppe_event'):
            Clock.unschedule(self.ppe_event)
        if hasattr(self, 'ppe_capture'):
            self.ppe_capture.release()
        self.clear_widgets()

class PPEImageScreen(Screen):
    def on_enter(self):
        self.clear_widgets()
        layout = BoxLayout(orientation='vertical')
        img = KivyImage(source='annotated_ppe_result.jpg')
        layout.add_widget(img)
        label = Label(text="Complete PPE: Access Granted!", font_size=20)
        layout.add_widget(label)
        self.add_widget(layout)
        Clock.schedule_once(self.reset_front_and_go_idle, 10)

    def reset_front_and_go_idle(self, dt):
        try:
            front_ref.set(0)
            print("🔄 front set to 0 in Firebase.")
        except Exception as e:
            print(f"❌ Error resetting front: {e}")
        self.manager.current = 'idle'

class CountdownCameraApp(App):
    def build(self):
        self.sm = ScreenManager()
        self.sm.add_widget(IdleScreen(name='idle'))
        self.sm.add_widget(CountdownScreen(name='countdown'))
        self.sm.add_widget(CameraScreen(name='camera'))
        self.sm.add_widget(AuthorizedAccessScreen(name='authorized_access'))
        self.sm.add_widget(PPEImageScreen(name='ppe_image'))
        self.sm.current = 'idle'
        return self.sm

if __name__ == '__main__':
    CountdownCameraApp().run()
