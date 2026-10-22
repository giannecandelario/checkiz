import os
import cv2
import numpy as np

def ela_ratio(img, boxes, quality=90) -> float:
    """Mean recompression error inside field boxes relative to the whole image."""
    ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    recompressed = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(img, recompressed).astype(np.float32).mean(axis=2)
    base = float(diff.mean()) + 1e-6
    ratios = []
    for x, y, w, h in boxes:
        region = diff[max(y, 0):y + h, max(x, 0):x + w]
        if region.size:
            ratios.append(float(region.mean()) / base)
    return max(ratios) if ratios else 0.0

def sharpness_ratio(img, boxes, pad=20) -> float:
    """Laplacian variance of field boxes vs the area around them."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    H, W = gray.shape
    ratios = []
    for x, y, w, h in boxes:
        inner = gray[y:y + h, x:x + w]
        y0, y1 = max(y - pad, 0), min(y + h + pad, H)
        x0, x1 = max(x - pad, 0), min(x + w + pad, W)
        outer = gray[y0:y1, x0:x1]
        if inner.size and outer.size:
            v_in = cv2.Laplacian(inner, cv2.CV_64F).var()
            v_out = cv2.Laplacian(outer, cv2.CV_64F).var() + 1e-6
            ratios.append(v_in / v_out)
    return max(ratios) if ratios else 0.0

# Starting thresholds. Tune these on your own real and edited samples.
# Override with env vars (CHECKIZ_ELA_THRESHOLD / CHECKIZ_SHARPNESS_THRESHOLD).
ELA_THRESHOLD = float(os.getenv("CHECKIZ_ELA_THRESHOLD", 8.0))
SHARPNESS_THRESHOLD = float(os.getenv("CHECKIZ_SHARPNESS_THRESHOLD", 6.0))

def forensic_report(img, boxes) -> dict:
    ela = ela_ratio(img, boxes)
    sharp = sharpness_ratio(img, boxes)
    return {
        "ela": round(ela, 2),
        "sharpness": round(float(sharp), 2),
        "flagged": bool(ela > ELA_THRESHOLD or sharp > SHARPNESS_THRESHOLD),
    }
