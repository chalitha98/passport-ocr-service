import os
import uuid
from flask import Flask, request, jsonify
from passporteye import read_mrz
import pytesseract
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"
app = Flask(__name__)

API_KEY = "internal-secret-key"

UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def process_passport_image(image_path):
    mrz = read_mrz(image_path)

    if mrz is None:
        return {
            "success": False,
            "error": "MRZ could not be detected",
            "score": 0
        }

    data = mrz.to_dict()

    return {
        "success": True,
        "score": mrz.valid_score,
        "passport_number": data.get("number"),
        "surname": data.get("surname"),
        "given_names": data.get("names"),
        "nationality": data.get("nationality"),
        "date_of_birth": data.get("date_of_birth"),
        "expiry_date": data.get("expiration_date"),
        "sex": data.get("sex")
    }

@app.route("/api/ocr/passport", methods=["POST"])
def passport_ocr():
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        return jsonify({
            "success": False,
            "error": "Unauthorized request"
        }), 401

    if "passport_image" not in request.files:
        return jsonify({
            "success": False,
            "error": "No passport image uploaded"
        }), 400

    file = request.files["passport_image"]

    if file.filename == "":
        return jsonify({
            "success": False,
            "error": "Empty file name"
        }), 400

    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        file.save(file_path)

        result = process_passport_image(file_path)

        return jsonify(result), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.route("/", methods=["GET"])
def health_check():
    return jsonify({
        "service": "OCR Passport Microservice",
        "status": "running"
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)