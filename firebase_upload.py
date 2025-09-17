import firebase_admin
from firebase_admin import credentials
from firebase_admin import db
import datetime

# Initialize Firebase Admin SDK
cred = credentials.Certificate("ode-project-734d6-firebase-adminsdk-fbsvc-619b1a34a2.json")
try:
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ode-project-734d6-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
except ValueError:
    # If the app was already initialized, get the existing app
    firebase_admin.get_app()

ref = db.reference('DWS-In-and-Out/')

now = datetime.datetime.now()
formatted_datetime = now.strftime("%Y-%m-%d %H:%M:%S")

users_ref = ref.child(formatted_datetime)
users_ref.set({'ID Number': '123123'})
print("Data successfully written to Firebase")
