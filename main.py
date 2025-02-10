import os
import uuid
import time
import requests
import random
import string
from flask import Flask, render_template, request, send_from_directory, url_for, jsonify
from PIL import Image
import pyheif
from threading import Thread

app = Flask(__name__)

# Configuration
app.config['UPLOAD_FOLDER_VIDEOS'] = 'uploads/videos'
app.config['UPLOAD_FOLDER_IMAGES'] = 'uploads/images'
app.config['ALLOWED_EXTENSIONS_VIDEO'] = {'mp4', 'avi', 'mov', 'mkv'}
app.config['ALLOWED_EXTENSIONS_IMAGE'] = {'jpg', 'jpeg', 'png', 'gif', 'heic'}
app.config['PREFERRED_URL_SCHEME'] = 'https'

os.makedirs(app.config['UPLOAD_FOLDER_VIDEOS'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_IMAGES'], exist_ok=True)

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in app.config['ALLOWED_EXTENSIONS_VIDEO'] | app.config['ALLOWED_EXTENSIONS_IMAGE']

def generate_unique_id():
    letters = string.ascii_uppercase
    part1 = ''.join(random.choice(letters) for _ in range(4))
    part2 = ''.join(random.choice(letters) for _ in range(4))
    part3 = ''.join(random.choice(letters) for _ in range(4))
    part4 = f"{random.randint(0, 9999):04d}"
    return f"{part1}-{part2}-{part3}-{part4}"

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty file'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_id = generate_unique_id()
    new_filename = f"{unique_id}.{ext}"

    if ext == 'heic':
        try:
            heif_file = pyheif.read(file.stream)
            image = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )
            new_filename = f"{unique_id}.jpg"
            image.save(os.path.join(app.config['UPLOAD_FOLDER_IMAGES'], new_filename), "JPEG")
            file_type = 'image'
        except Exception as e:
            return jsonify({'error': f'HEIC conversion failed: {str(e)}'}), 500
    else:
        file_type = 'video' if ext in app.config['ALLOWED_EXTENSIONS_VIDEO'] else 'image'
        folder = app.config['UPLOAD_FOLDER_VIDEOS'] if file_type == 'video' else app.config['UPLOAD_FOLDER_IMAGES']
        file.save(os.path.join(folder, new_filename))

    file_url = url_for(
        'serve_file',
        folder=('videos' if file_type == 'video' else 'images'),
        filename=new_filename,
        _external=True
    )

    return jsonify({'url': file_url, 'type': file_type})

@app.route('/uploads/<folder>/<filename>')
def serve_file(folder, filename):
    directory = app.config[f'UPLOAD_FOLDER_{folder.upper()}']
    return send_from_directory(directory, filename)

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive"})

def keep_alive():
    url = "https://your-app-name.onrender.com/ping"  # আপনার অ্যাপের URL দিয়ে পরিবর্তন করুন
    while True:
        time.sleep(300)
        try:
            response = requests.get(url)
            print("✅ Ping successful" if response.status_code == 200 else f"⚠️ Ping failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == '__main__':
    Thread(target=keep_alive, daemon=True).start()
    app.run(debug=True, host='0.0.0.0', port=3000)
