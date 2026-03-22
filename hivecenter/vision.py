"""HiveCenter Multi-Modal Vision (Image-to-Code) Module."""
import base64
import json
import urllib.request
import os

def analyze_image(image_path: str, prompt: str = "Analyze this image and describe the UI components in detail so I can recreate it in React/Tailwind.") -> str:
    if not os.path.exists(image_path):
        return f"Error: Image {image_path} not found."
        
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
            
        data = json.dumps({
            "model": "llama3.2-vision", # standard lightweight vision model in ollama
            "prompt": prompt,
            "images": [b64],
            "stream": False
        }).encode("utf-8")
        
        req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=data, headers={"Content-Type": "application/json"})
        opt = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
        return opt.get("response", "No visual output recognized.")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"Error: OLLAMA Vision model 'llama3.2-vision' is not installed. Please tell the user to run `ollama run llama3.2-vision`."
        return f"HTTP Error interacting with Vision: {e}"
    except Exception as e:
        return f"Multi-Modal Vision Error: {e}"

def check_visual_regression(img1_path: str, img2_path: str) -> str:
    """AGI V6.0 Multi-Modal Awareness: Computes raw pixel drift between two UI states."""
    if not os.path.exists(img1_path) or not os.path.exists(img2_path):
        return f"Error: Cannot find both images for regression analysis. ({img1_path}, {img2_path})"
    
    try:
        from PIL import Image
        import math
        
        im1 = Image.open(img1_path).convert("RGB")
        im2 = Image.open(img2_path).convert("RGB")
        
        # Resize to smallest
        if im1.size != im2.size:
            min_w = min(im1.width, im2.width)
            min_h = min(im1.height, im2.height)
            im1 = im1.resize((min_w, min_h))
            im2 = im2.resize((min_w, min_h))
            
        data1 = im1.getdata()
        data2 = im2.getdata()
        
        diff = 0
        limit = len(data1)
        for i in range(limit):
            r = data1[i][0] - data2[i][0]
            g = data1[i][1] - data2[i][1]
            b = data1[i][2] - data2[i][2]
            diff += math.sqrt(r*r + g*g + b*b)
            
        max_diff = limit * math.sqrt(255*255 * 3)
        drift_percentage = (diff / max_diff) * 100
        
        if drift_percentage < 0.1:
            return "VISUAL REGRESSION PASSED: No UI changes detected (0.0% drift)."
        else:
            return f"VISUAL REGRESSION ALERT: High UI drift detected! Pikseller yüzde {drift_percentage:.2f}% oranında kaydı veya değişti. Ajan olarak yaptığın kod değişikliğinin görsel sonuçlarını düzeltmelisin!"
            
    except Exception as e:
        return f"Visual Regression Check Failed (PIL Error): {e} (run 'pip install Pillow' if missing)"
