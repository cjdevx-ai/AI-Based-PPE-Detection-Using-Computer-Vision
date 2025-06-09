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
from PIL import Image, ImageDraw, ImageFont
from inference_sdk import InferenceHTTPClient
import threading
import time
import os

# --- Camera Indexes ---
qr_cam_index_front = 1
qr_cam_index_back = 0
ppe_cam_index = 2

# --- Firebase Initialization ---
cred = credentials.Certificate("ode-project-734d6-firebase-adminsdk-fbsvc-5699f7abc3.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ode-project-734d6-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })

ref = db.reference('/')
front_ref = db.reference('/front')
back_ref = db.reference('/back')
door_status_ref = db.reference('/door_status')
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
        threading.Thread(target=self.poll_firebase, daemon=True).start()

    def poll_firebase(self):
        while True:
            try:
                front_value = front_ref.get()
                back_value = back_ref.get()
                if front_value == 1:
                    print("🔑 Front = 1 detected. Proceeding to front QR scan.")
                    Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'countdown_front'))
                    break
                elif back_value == 1:
                    print("🔑 Back = 1 detected. Proceeding to back QR scan.")
                    Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'countdown_back'))
                    break
            except Exception as e:
                print(f"Error polling Firebase: {e}")
            time.sleep(1)

class CountdownScreen(Screen):
    def __init__(self, camera_target, next_screen, **kwargs):
        super().__init__(**kwargs)
        self.camera_target = camera_target
        self.next_screen = next_screen

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
            self.manager.current = self.next_screen

class CameraScreen(Screen):
    def __init__(self, cam_index, is_back=False, **kwargs):
        super().__init__(**kwargs)
        self.cam_index = cam_index
        self.is_back = is_back

    def on_enter(self):
        self.capture = cv2.VideoCapture(self.cam_index)
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
                print(f"📥 Scanned and uploaded: {barcode_data}")
                if self.is_back:
                    back_ref.set(0)
                    door_status_ref.set(1)
                    print("✅ Back reset to 0 and door_status set to 1 in Firebase.")
                    self.manager.current = 'idle'
                else:
                    self.manager.get_screen('authorized_access').current_timestamp = formatted_datetime
                    self.manager.current = 'authorized_access'
                Clock.unschedule(self.event)
                self.capture.release()
                return
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
            self.label.text = "❌ Inference failed. Retrying..."
            os.remove(image_path)
            self.restart_countdown()
            return

        draw = ImageDraw.Draw(image, "RGBA")
        class_colors = {
            "hardhat": (255, 255, 0, 200),
            "vest": (128, 0, 128, 200),
            "gloves": (255, 0, 0, 200)
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
            color = class_colors.get(label, (255, 255, 255, 200))
            draw.rectangle([x0, y0, x1, y1], outline=color[:3])
            draw.text((x0, y0-25), f"{label} ({confidence:.2f})", fill=(255,255,255), font=font)

        annotated_path = "annotated_ppe_result.jpg"
        image.save(annotated_path)
        hardhat = int("hardhat" in detected_items)
        vest = int("vest" in detected_items)
        gloves = int("gloves" in detected_items)

        if self.current_timestamp:
            ppe_ref = qr_data_ref.child(self.current_timestamp)
            ppe_ref.update({
                "hardhat": hardhat,
                "vest": vest,
                "gloves": gloves
            })

        if hardhat and vest and gloves:
            self.label.text = "✅ Access Granted: Complete PPE Detected"
            door_status_ref.set(1)  # <--- Added this line to set door_status to 1
            Clock.schedule_once(lambda dt: setattr(self.manager, 'current', 'ppe_image'), 2)
        else:
            self.label.text = "❌ Incomplete PPE. Retrying..."
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
        front_ref.set(0)
        self.manager.current = 'idle'

# --- App ---
class CountdownCameraApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(IdleScreen(name='idle'))
        sm.add_widget(CountdownScreen(name='countdown_front', camera_target='front', next_screen='camera_front'))
        sm.add_widget(CountdownScreen(name='countdown_back', camera_target='back', next_screen='camera_back'))
        sm.add_widget(CameraScreen(name='camera_front', cam_index=qr_cam_index_front, is_back=False))
        sm.add_widget(CameraScreen(name='camera_back', cam_index=qr_cam_index_back, is_back=True))
        sm.add_widget(AuthorizedAccessScreen(name='authorized_access'))
        sm.add_widget(PPEImageScreen(name='ppe_image'))
        sm.current = 'idle'
        return sm

if __name__ == '__main__':
    CountdownCameraApp().run()
