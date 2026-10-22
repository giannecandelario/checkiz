"""Generate synthetic demo receipts into ../samples (no real GCash/Maya data).
real.png     matches the seeded ledger entry (1002849130490, PHP 1,250.00)
edited.png   same receipt with the amount pasted over to PHP 9,250.00
Replace these with real screenshots when you have them."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "samples"
OUT.mkdir(exist_ok=True)

def font(size):
    for name in ("DejaVuSans.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()

def receipt(amount="1,250.00", ref="1002 849 130490"):
    im = Image.new("RGB", (600, 800), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 600, 110], fill=(0, 112, 224))
    d.text((30, 35), "Express Send  |  Sent", fill="white", font=font(34))
    d.text((30, 170), "Amount", fill=(90, 90, 90), font=font(26))
    d.text((30, 210), f"PHP {amount}", fill="black", font=font(44))
    d.text((30, 330), "Sent to  MARIA S. 0917 *** 1234", fill="black", font=font(26))
    d.text((30, 440), "Ref No.", fill=(90, 90, 90), font=font(26))
    d.text((30, 480), ref, fill="black", font=font(40))
    d.text((30, 600), "Oct 22, 2026  10:14 AM", fill=(90, 90, 90), font=font(24))
    return im.filter(ImageFilter.GaussianBlur(0.6))

real = receipt()
real.save(OUT / "real.png")

edited = real.copy()
d = ImageDraw.Draw(edited)
d.rectangle([25, 205, 360, 270], fill="white")           # crisp pasted patch
d.text((30, 210), "PHP 9,250.00", fill="black", font=font(44))
edited.save(OUT / "edited.png")
print("Wrote", OUT / "real.png", "and", OUT / "edited.png")
