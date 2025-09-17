from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt

# Load the image
image_path = "ppe_capture.jpg"
image = Image.open(image_path).convert("RGB")

# Initialize Roboflow client
CLIENT = InferenceHTTPClient(
    api_url="https://serverless.roboflow.com",
    api_key="ipRXafHM2fxthdHpXUSC"
)

# Run inference
result = CLIENT.infer(image_path, model_id="ppe-ukjvg/2")

# Prepare for drawing
draw = ImageDraw.Draw(image, "RGBA")

# Fixed colors per class
class_colors = {
    "hardhat": (255, 255, 0, 200),     # Yellow
    "vest": (128, 0, 128, 200),        # Purple
    "gloves": (255, 0, 0, 200),        # Red
    "shoes": (0, 255, 255, 200),       # Cyan
}

# Load font
try:
    font = ImageFont.truetype("arial.ttf", 50)
except:
    font = ImageFont.load_default()

# Draw predictions
for pred in result["predictions"]:
    x0 = pred["x"] - pred["width"] / 2
    y0 = pred["y"] - pred["height"] / 2
    x1 = x0 + pred["width"]
    y1 = y0 + pred["height"]
    label = f"{pred['class']} ({pred['confidence']:.2f})"

    # Get color by class, fallback to white
    color = class_colors.get(pred["class"], (255, 255, 255, 200))

    # Draw thicker bounding box (20px)
    for offset in range(5):
        draw.rectangle([x0 - offset, y0 - offset, x1 + offset, y1 + offset], outline=color[:3])

    # Calculate text background box
    text_bbox = draw.textbbox((x0, y0), label, font=font)
    text_x0, text_y0, text_x1, text_y1 = text_bbox
    text_height = text_y1 - text_y0
    text_width = text_x1 - text_x0

    # Draw background for label
    draw.rectangle([x0, y0 - text_height - 10, x0 + text_width + 10, y0], fill=color)

    # Draw label text
    draw.text((x0 + 5, y0 - text_height - 5), label, fill=(255, 255, 255), font=font)

# Show result
plt.figure(figsize=(12, 10))
plt.imshow(image)
plt.axis("off")
plt.title("Detected Objects (Color-Coded)", fontsize=18)
plt.tight_layout()
plt.show()
