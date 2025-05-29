# AI-Based PPE Detection Using Computer Vision

This repository contains a Python script for detecting Personal Protective Equipment (PPE) in images using a Roboflow computer vision model. The model detects PPE items such as hardhats, vests, gloves, and shoes, and visualizes the results with color-coded bounding boxes and confidence scores.

---

## Features

- Detects multiple PPE classes: hardhat, vest, gloves, shoes
- Uses Roboflow's Inference HTTP API for model predictions
- Draws color-coded bounding boxes around detected PPE
- Displays confidence scores on the image
- Visualizes results with Matplotlib

---

## Requirements

- Python 3.x
- `Pillow`
- `matplotlib`
- `inference_sdk` (Roboflow's inference client)

You can install the Python dependencies with:

```bash
pip install Pillow matplotlib inference_sdk
