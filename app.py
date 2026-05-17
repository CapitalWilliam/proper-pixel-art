"""Flask entry point for WeChat CloudBase Run."""

import base64
import io
import os

from flask import Flask, jsonify, request
from PIL import Image

from proper_pixel_art.pixelate import pixelate

app = Flask(__name__)


@app.route("/")
def index() -> str:
    return "Proper Pixel Art API is running"


@app.route("/api/health", methods=["GET"])
def health() -> dict:
    return jsonify({"status": "ok"})


@app.route("/api/pixelate", methods=["POST"])
def pixelate_endpoint() -> tuple:
    if "image" not in request.files:
        return jsonify({"success": False, "error": "No image file provided"}), 400

    file = request.files["image"]
    if not file or file.filename == "":
        return jsonify({"success": False, "error": "Empty file"}), 400

    try:
        img = Image.open(file.stream)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Cannot open image: {exc}"}), 400

    num_colors = request.form.get("num_colors", type=int)
    transparent = request.form.get("transparent", "false").lower() == "true"
    scale_result = request.form.get("scale_result", 1, type=int)
    crop_to_square = request.form.get("crop_to_square", "true").lower() == "true"
    pixel_width = request.form.get("pixel_width", type=int)
    initial_upscale = request.form.get("initial_upscale", 2, type=int)

    try:
        result = pixelate(
            img,
            num_colors=num_colors,
            transparent_background=transparent,
            scale_result=scale_result if scale_result > 1 else None,
            crop_to_square=crop_to_square,
            pixel_width=pixel_width,
            initial_upscale_factor=initial_upscale,
        )
    except Exception as exc:
        return jsonify({"success": False, "error": f"Pixelation failed: {exc}"}), 500

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    w, h = result.size

    return jsonify(
        {
            "success": True,
            "image_base64": b64,
            "width": w,
            "height": h,
            "format": "png",
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    app.run(host="0.0.0.0", port=port)
