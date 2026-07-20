from PIL import Image
import os

asset_dir = "src/assets"

for filename in os.listdir(asset_dir):
    if filename.endswith(".png"):
        filepath = os.path.join(asset_dir, filename)
        
        try:
            img = Image.open(filepath)
            # 50x50 piksel boyutu
            img = img.resize((50, 50), Image.Resampling.LANCZOS)
            # Aynı isimle üzerine yaz
            img.save(filepath, optimize=True, quality=85)
            print(f"{filename}")
        except Exception as e:
            print(f"error - {filename}: {e}")

