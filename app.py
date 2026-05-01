"""
Passport OCR Microservice for the HBMS (Hotel Booking Management System).

This Flask application provides a REST API for extracting passport
MRZ (Machine Readable Zone) data using PassportEye and Tesseract OCR.
It is designed to run as a standalone Docker container and is called
internally by the PHP backend during the KYC verification process.

Endpoint:
    POST /api/ocr/passport

Accepted formats: JPEG, PNG (max 5 MB)
Authentication: X-API-KEY header
"""

import os
import uuid
from flask import Flask, request, jsonify
from passporteye import read_mrz
from dotenv import load_dotenv
import cv2
import numpy as np
import pytesseract



# Load environment variables from .env file
load_dotenv()

# Set the path to the Tesseract binary installed in the Docker container
pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

app = Flask(__name__)

### Lets remove this harcoded key its a very unsafe practice
# API_KEY = "internal-secret-key"

# The API key is read from the environment so it is not hardcoded in source.
API_KEY = os.getenv("OCR_API_KEY")

# Temporary folder used to save uploaded images during processing.
# Files are deleted immediately after OCR extraction (guys, see finally block).
UPLOAD_FOLDER = "temp_uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# Upload validation limits to avoid oversized files from
# consuming CPU during OCR processing.
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB



def preprocess_image(image_path):
    """
    Apply gentle image processing to improve OCR results.
    We use a Bilateral Filter which is great at removing background 
    noise (like the mountains) while keeping the text edges sharp.
    """
    img = cv2.imread(image_path)
    if img is None:
        return image_path

    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Resizing can help Tesseract 'see' the shapes better
    # We only resize if the image is relatively small
    height, width = gray.shape
    if width < 2000:
        gray = cv2.resize(gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LANCZOS4)

    # 3. Bilateral Filter: Smooths the background but preserves the text edges
    # This is excellent for removing the mountain patterns in your sample
    processed = cv2.bilateralFilter(gray, 9, 75, 75)

    # Save the processed image
    processed_path = image_path.replace(".", "_proc.")
    cv2.imwrite(processed_path, processed)
    
    return processed_path

def allowed_file(filename):
    """Return True if the filename has an allowed image extension."""
    return "." in filename and \
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def process_passport_image(image_path):
    """
        Use PassportEye to detect and parse the MRZ from a passport image.

        Returns a dictionary of extracted fields if successful, or None
        if the MRZ could not be detected in the image.
    """

    # Step A: Pre-process the image to make it easier for OCR
    processed_path = preprocess_image(image_path)
    
    # Step B: Run PassportEye on the improved image
    mrz = read_mrz(processed_path)

    # Clean up the processed temporary file
    if processed_path != image_path and os.path.exists(processed_path):
        os.remove(processed_path)


    # @suman -> i have removed the return json with success flag and 
    # error message because this is a helper function and it should only return 
    # the extracted data and the score. The route will handle the success flag 
    # and error message.
    if mrz is None:
        return None

    data = mrz.to_dict()

    # valid_score represents how many of the MRZ check digits passed (0-100).
    # A score of 50 or above is treated as a valid document.
    mrz_valid = mrz.valid_score >= 50

    # return {
    #     "success": True,
    #     "score": mrz.valid_score,
    #     "passport_number": data.get("number"),
    #     "surname": data.get("surname"),
    #     "given_names": data.get("names"),
    #     "nationality": data.get("nationality"),
    #     "date_of_birth": data.get("date_of_birth"),
    #     "expiry_date": data.get("expiration_date"),
    #     "sex": data.get("sex")
    # }

    # @Suman -> I have removed the success flag this will be handles in route this 
    # helper will only send the extracted data and the score.
    return {
        "document_type": data.get("type", "P"),
        "surname": data.get("surname", ""),
        "given_names": data.get("names", ""),
        "nationality": data.get("nationality", ""),
        "date_of_birth": data.get("date_of_birth", ""),
        "gender": data.get("sex", ""),
        "passport_number": data.get("number", ""),
        "expiry_date": data.get("expiration_date", ""),
        "issuing_country": data.get("country", ""),
        "mrz_checksum_valid": mrz_valid,
        "mrz_valid_score": mrz.valid_score,
    }

@app.route("/api/ocr/passport", methods=["POST"])
def passport_ocr():
    """Handle passport image upload and return extracted MRZ data."""

    #Step 1 - verify the request has a valid API Key
    client_key = request.headers.get("X-API-KEY")

    if client_key != API_KEY:
        return jsonify({
            "success": False,
            "error": "Unauthorized request"
        }), 401

    #Step 2 – check that file was included in the request
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
    
    #Step 3 – validate the file extension
    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
    }), 400

    #Step 4 – vaalidate the file size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > MAX_FILE_SIZE:
        return jsonify({
            "success": False,
            "error": f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
        }), 400

    #step 5 – save temporarily, run OCR, then clean up
    filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        file.save(file_path)
        result = process_passport_image(file_path)
        # @Chalitha - your original route just pass through whatever the helper returns
        # We moved the JSON/HTTP logic here from the helper for better code structure.
        if result is None:
            return jsonify({
                "success": False,
                "error": "Could not extract MRZ from image. "
                         "Please re-upload a clearer photo."
            }), 422

        return jsonify({
            "success": True,
            "data": result
        }), 200

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

    finally:
        # Remove the uploaded image file regardless of success or failure.
        # Passport images must not be storeed on disk.
        if os.path.exists(file_path):
            os.remove(file_path)


@app.route("/", methods=["GET"])
def health_check():
    """Simple health check used to verify the service is running."""
    return jsonify({
        "service": "HBMS Passport OCR Microservice",
        "status": "running",
        "version": "1.0.0"
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=True)