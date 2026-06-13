---
name: qr-decode-from-image
description: Decode QR codes embedded in image files (screenshots, photos) using pyzbar. Use when the user sends an image with a QR code and you need the encoded URL or text.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [QR Code, Image, Decoding, Scanning]
---

# QR Code Decoding from Image Files

Decode QR codes embedded in image files using pyzbar. Use when the user sends an image with a QR code and you need the encoded URL or text.

## Prerequisites (one-time setup)

Install system library + Python package:
```bash
sudo apt-get update -qq && sudo apt-get install -y -qq libzbar0
pip install pyzbar Pillow
```

If `sudo` fails (no permission in sandbox), libzbar0 may already be present — just install pyzbar.

## Usage

```python
from pyzbar.pyzbar import decode
from PIL import Image

img = Image.open('/path/to/image.jpg')
results = decode(img)

if results:
    for r in results:
        print(f"Type: {r.type}")
        print(f"Data: {r.data.decode('utf-8')}")
else:
    print("No QR code detected")
```

## Notes
- Can detect multiple QR codes in one image — iterate all results
- Data is usually a URL string; decode from UTF-8
- If pyzbar is already installed, skip pip step — just try importing first
- Fallback: if pyzbar fails, try OpenCV: `cv2.QRCodeDetector().detectAndDecode()`