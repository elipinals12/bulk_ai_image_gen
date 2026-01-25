"""
Quick API Key Test Script
Tests which Gemini models your API key can access
"""

import requests
import json

# Load API key
try:
    with open('apikey.txt', 'r') as f:
        API_KEY = f.read().strip()
except:
    print("ERROR: apikey.txt not found!")
    exit()

print("="*60)
print("TESTING YOUR GEMINI API KEY")
print("="*60)

# Models to test (in order of accessibility)
models_to_test = [
    ("gemini-2.5-flash", "2.5 Flash (text)"),
    ("gemini-2.5-flash-image", "2.5 Flash Image (most accessible image model)"),
    ("gemini-3-flash-preview", "3 Flash (text)"),
    ("gemini-3-pro-preview", "3 Pro (text)"),
    ("gemini-3-pro-image-preview", "3 Pro Image / Nano Banana Pro (4K)")
]

print(f"\nTesting {len(models_to_test)} models...\n")

accessible_models = []
restricted_models = []

for model, description in models_to_test:
    print(f"Testing {description}...")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    headers = {
        "x-goog-api-key": API_KEY,
        "Content-Type": "application/json"
    }
    
    # Simple test request
    body = {
        "contents": [{
            "parts": [{"text": "Hi"}]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        
        if response.status_code == 200:
            print(f"  ✓ ACCESSIBLE - {model}\n")
            accessible_models.append((model, description))
        elif response.status_code == 403:
            print(f"  ✗ 403 FORBIDDEN - No access to {model}\n")
            restricted_models.append((model, description))
        elif response.status_code == 404:
            print(f"  ✗ 404 NOT FOUND - Model doesn't exist\n")
        else:
            print(f"  ? {response.status_code} - {response.text[:100]}\n")
    
    except Exception as e:
        print(f"  ✗ ERROR: {str(e)[:100]}\n")

# Summary
print("="*60)
print("RESULTS")
print("="*60)

if accessible_models:
    print(f"\n✓ YOU HAVE ACCESS TO ({len(accessible_models)} models):")
    for model, desc in accessible_models:
        print(f"  - {desc}")
        print(f"    Model: {model}")

if restricted_models:
    print(f"\n✗ YOU DON'T HAVE ACCESS TO ({len(restricted_models)} models):")
    for model, desc in restricted_models:
        print(f"  - {desc}")
        print(f"    Model: {model}")

print("\n" + "="*60)
print("RECOMMENDATION")
print("="*60)

if any("3-pro-image" in m[0] for m in accessible_models):
    print("\n🎉 YOU HAVE GEMINI 3 PRO IMAGE ACCESS!")
    print("   Use model: gemini-3-pro-image-preview")
elif any("2.5-flash-image" in m[0] for m in accessible_models):
    print("\n✓ You can use: gemini-2.5-flash-image (1024px)")
    print("  This is reliable and widely accessible.")
    print("\n  To get 4K (Gemini 3 Pro Image):")
    print("  1. Subscribe to Google AI Ultra ($20/month)")
    print("  2. OR join waitlist (no guarantee when)")
else:
    print("\n✗ No image generation models accessible!")
    print("  Your API key may be invalid or restricted.")

print("="*60)