import firebase_admin
from firebase_admin import credentials, db
import time

# Initialize Firebase Admin SDK with the new credential
cred = credentials.Certificate("ode-project-734d6-firebase-adminsdk-fbsvc-619b1a34a2.json")
try:
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://ode-project-734d6-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
except ValueError:
    # App already initialized
    pass

# Reference the root path where timestamp nodes are stored
ref = db.reference('/')

while True:
    # Fetch current values
    data = ref.get()

    # Extract values for 'back' and 'front'
    back_value = data.get('back', 0)
    front_value = data.get('front', 0)

    # Print values
    print(f"Back: {back_value}, Front: {front_value}")

    # Check if either one is 1
    if back_value == 1 or front_value == 1:
        print("1 detected")
        break

    # Wait a short time before checking again (to avoid hammering the server)
    time.sleep(1)
