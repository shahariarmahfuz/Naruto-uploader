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
app.secret_key = 'your_secret_key_here'

# Configuration
app.config['UPLOAD_FOLDER_VIDEOS'] = 'uploads/videos'
app.config['UPLOAD_FOLDER_IMAGES'] = 'uploads/images'
app.config['LINKS_FILE'] = 'link.json'
app.config['ITEMS_PER_PAGE'] = 10
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

def process_file_upload(file, client_ip):
    try:
        if file.filename == '':
            return {'error': 'Empty file'}

        if not allowed_file(file.filename):
            return {'error': 'Invalid file type'}

        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_id = generate_unique_id()
        new_filename = f"{unique_id}.{ext}"
        upload_time = get_bangladesh_time()

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
                return {'error': f'HEIC conversion failed: {str(e)}'}
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

        links = load_links()
        links.insert(0, {
            "url": file_url,
            "type": file_type,
            "id": unique_id,
            "time": upload_time,
            "ip": client_ip
        })
        save_links(links)

        return {'url': file_url, 'type': file_type}

    except Exception as e:
        return {'error': f'Internal server error: {str(e)}'}

@app.route('/')
def index():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def handle_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file selected'}), 400

    file = request.files['file']
    client_ip = request.remote_addr

    result = process_file_upload(file, client_ip)
    if 'error' in result:
        return jsonify({'error': result['error']}), 400
    return jsonify({'url': result['url'], 'type': result['type']})

@app.route('/api', methods=['POST'])
def handle_api_upload():
    if 'file' not in request.files:
        return jsonify({'status': 'fail', 'link': None}), 400

    file = request.files['file']
    client_ip = request.remote_addr

    result = process_file_upload(file, client_ip)
    if 'error' in result:
        return jsonify({'status': 'fail', 'link': None}), 400
    return jsonify({'status': 'success', 'link': result['url']})

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

    url_parts = link_to_delete['url'].split('/')
    filename = url_parts[-1]
    folder_type = 'VIDEOS' if link_to_delete['type'] == 'video' else 'IMAGES'
    file_path = os.path.join(app.config[f'UPLOAD_FOLDER_{folder_type}'], filename)

    try:
        os.remove(file_path)
    except Exception as e:
        print(f"Error deleting file: {str(e)}")
        flash('Error deleting file!', 'error')
        return redirect(url_for('get_links_html'))

    new_links = [link for link in links if link['id'] != link_id]
    save_links(new_links)

    flash('File deleted successfully!', 'success')
    return redirect(url_for('get_links_html'))

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive"})

@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.route('/cloud', methods=['GET', 'POST'])
def cloud_upload():
    if request.method == 'POST':
        url = request.form.get('url')
        if not url:
            flash('Please provide a valid URL', 'error')
            return redirect(url_for('cloud_upload'))
        
        try:
            filename = url.split('/')[-1].split('?')[0]
            if '.' not in filename:
                flash('URL must point to a file with extension', 'error')
                return redirect(url_for('cloud_upload'))
            
            ext = filename.rsplit('.', 1)[1].lower()
            if ext not in app.config['ALLOWED_EXTENSIONS_VIDEO'] | app.config['ALLOWED_EXTENSIONS_IMAGE']:
                flash('File type not allowed', 'error')
                return redirect(url_for('cloud_upload'))
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            file_type = 'video' if ext in app.config['ALLOWED_EXTENSIONS_VIDEO'] else 'image'
            folder = app.config['UPLOAD_FOLDER_VIDEOS'] if file_type == 'video' else app.config['UPLOAD_FOLDER_IMAGES']
            
            unique_id = generate_unique_id()
            new_filename = f"{unique_id}.{ext}"
            file_path = os.path.join(folder, new_filename)
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            if ext == 'heic':
                try:
                    with open(file_path, 'rb') as f:
                        heif_file = pyheif.read(f.read())
                    image = Image.frombytes(
                        heif_file.mode,
                        heif_file.size,
                        heif_file.data,
                        "raw",
                        heif_file.mode,
                        heif_file.stride,
                    )
                    new_filename = f"{unique_id}.jpg"
                    jpg_path = os.path.join(app.config['UPLOAD_FOLDER_IMAGES'], new_filename)
                    image.save(jpg_path, "JPEG")
                    os.remove(file_path)
                    file_type = 'image'
                    folder = app.config['UPLOAD_FOLDER_IMAGES']
                    ext = 'jpg'
                except Exception as e:
                    os.remove(file_path)
                    flash('HEIC conversion failed', 'error')
                    return redirect(url_for('cloud_upload'))
            
            file_url = url_for(
                'serve_file',
                folder=('videos' if file_type == 'video' else 'images'),
                filename=new_filename,
                _external=True
            )
            
            client_ip = request.remote_addr
            upload_time = get_bangladesh_time()
            links = load_links()
            links.insert(0, {
                "url": file_url,
                "type": file_type,
                "id": unique_id,
                "time": upload_time,
                "ip": client_ip
            })
            save_links(links)
            
            flash(f'File uploaded successfully! <a href="{file_url}">View File</a>', 'success')
            return redirect(url_for('cloud_upload'))
        
        except requests.exceptions.RequestException as e:
            flash(f'Error downloading file: {str(e)}', 'error')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')
        
        return redirect(url_for('cloud_upload'))
    
    return render_template('cloud_upload.html')

def keep_alive():
    url = "https://naruto-uploader.onrender.com/ping"
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
