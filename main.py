import os
import time
import requests
import random
import string
import json
import pytz
from datetime import datetime
from flask import Flask, render_template, request, send_from_directory, url_for, jsonify, redirect, flash
from PIL import Image
import pyheif
from threading import Thread

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # ফ্লাস্কের জন্য সিক্রেট কী

# Configuration
app.config['UPLOAD_FOLDER_VIDEOS'] = 'uploads/videos'
app.config['UPLOAD_FOLDER_IMAGES'] = 'uploads/images'
app.config['LINKS_FILE'] = 'link.json'
app.config['ITEMS_PER_PAGE'] = 20
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['ALLOWED_EXTENSIONS_VIDEO'] = {'mp4', 'avi', 'mov', 'mkv'}
app.config['ALLOWED_EXTENSIONS_IMAGE'] = {'jpg', 'jpeg', 'png', 'gif', 'heic'}

os.makedirs(app.config['UPLOAD_FOLDER_VIDEOS'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER_IMAGES'], exist_ok=True)

def load_links():
    if os.path.exists(app.config['LINKS_FILE']):
        with open(app.config['LINKS_FILE'], 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_links(links):
    with open(app.config['LINKS_FILE'], 'w', encoding='utf-8') as f:
        json.dump(links, f, indent=4, ensure_ascii=False)

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in app.config['ALLOWED_EXTENSIONS_VIDEO'] | app.config['ALLOWED_EXTENSIONS_IMAGE']

def generate_unique_id():
    letters = string.ascii_uppercase
    return '-'.join([''.join(random.choice(letters) for _ in range(4)) for _ in range(3)]) + f"-{random.randint(0, 9999):04d}"

def get_bangladesh_time():
    bd_tz = pytz.timezone("Asia/Dhaka")
    return datetime.now(bd_tz).strftime("%Y-%m-%d %I:%M %p")

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
    client_ip = request.remote_addr  # IP Address
    upload_time = get_bangladesh_time()  # BD Time

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

    # Save link with time and IP
    links = load_links()
    links.insert(0, {"url": file_url, "type": file_type, "id": unique_id, "time": upload_time, "ip": client_ip})
    save_links(links)

    return jsonify({'url': file_url, 'type': file_type})

@app.route('/uploads/<folder>/<filename>')
def serve_file(folder, filename):
    directory = app.config[f'UPLOAD_FOLDER_{folder.upper()}']
    return send_from_directory(directory, filename)

@app.route('/link', methods=['GET'])
def get_links_html():
    page = request.args.get('page', 1, type=int)
    links = load_links()

    start = (page - 1) * app.config['ITEMS_PER_PAGE']
    end = start + app.config['ITEMS_PER_PAGE']
    paginated_links = links[start:end]

    next_page = page + 1 if end < len(links) else None
    prev_page = page - 1 if page > 1 else None

    return render_template('links.html', 
                           links=paginated_links, 
                           current_page=page, 
                           next_page=next_page, 
                           prev_page=prev_page)

@app.route('/delete/<string:link_id>', methods=['POST'])
def delete_link(link_id):
    links = load_links()
    link_to_delete = next((link for link in links if link['id'] == link_id), None)
    
    if not link_to_delete:
        flash('Link not found!', 'error')
        return redirect(url_for('get_links_html'))

    # ফাইল পাথ তৈরি
    url_parts = link_to_delete['url'].split('/')
    filename = url_parts[-1]
    folder_type = 'VIDEOS' if link_to_delete['type'] == 'video' else 'IMAGES'
    file_path = os.path.join(app.config[f'UPLOAD_FOLDER_{folder_type}'], filename)

    # ফাইল ডিলিট
    try:
        os.remove(file_path)
    except Exception as e:
        print(f"Error deleting file: {str(e)}")
        flash('Error deleting file!', 'error')
        return redirect(url_for('get_links_html'))

    # লিঙ্ক লিস্ট আপডেট
    new_links = [link for link in links if link['id'] != link_id]
    save_links(new_links)

    flash('File deleted successfully!', 'success')
    return redirect(url_for('get_links_html'))

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive"})

# 404 Error Handler
@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

def keep_alive():
    url = "https://naruto-uploader.onrender.com/ping"  # আপনার অ্যাপের URL দিয়ে পরিবর্তন করুন
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
