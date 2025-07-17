#!/usr/bin/env python3

import os
import uuid
import json
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import threading
import time

# Import the Inky library
from inky.auto import auto

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = 'your-secret-key-change-this'  # Change this to a random secret key

# Configuration
UPLOAD_FOLDER = 'static/uploads'
THUMBNAILS_FOLDER = 'static/thumbnails'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAILS_FOLDER, exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Global variable to track current display
current_display_image = None
display_lock = threading.Lock()

def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_thumbnail(input_path, output_path, size=(200, 200)):
    """Create a thumbnail of the uploaded image."""
    try:
        with Image.open(input_path) as img:
            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            
            # Create thumbnail
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(output_path, 'JPEG', quality=85)
            return True
    except Exception as e:
        print(f"Error creating thumbnail: {e}")
        return False

def get_image_list():
    """Get list of all uploaded images with their metadata."""
    images = []
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            if allowed_file(filename):
                image_path = os.path.join(UPLOAD_FOLDER, filename)
                thumbnail_path = os.path.join(THUMBNAILS_FOLDER, f"thumb_{filename}")
                
                # Create thumbnail if it doesn't exist
                if not os.path.exists(thumbnail_path):
                    print(f"Creating thumbnail for {filename}")
                    create_thumbnail(image_path, thumbnail_path)
                
                images.append({
                    'filename': filename,
                    'upload_time': os.path.getctime(image_path)
                })
    
    # Sort by upload time (newest first)
    images.sort(key=lambda x: x['upload_time'], reverse=True)
    return images

def display_image_on_eink(image_path, saturation=0.5):
    """Display an image on the e-ink display."""
    global current_display_image
    
    with display_lock:
        try:
            # Initialize the display
            inky = auto(ask_user=False, verbose=True)
            
            # Open and resize the image
            image = Image.open(image_path)
            resized_image = image.resize(inky.resolution)
            
            # Set the image on the display
            try:
                inky.set_image(resized_image, saturation=saturation)
            except TypeError:
                # Fallback for displays that don't support saturation
                inky.set_image(resized_image)
            
            # Update the display
            inky.show()
            
            current_display_image = os.path.basename(image_path)
            return True, "Image displayed successfully"
            
        except Exception as e:
            return False, f"Error displaying image: {str(e)}"

@app.route('/')
def index():
    """Main page showing all uploaded images."""
    images = get_image_list()
    return render_template('index.html', images=images, current_image=current_display_image)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload."""
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4()}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        file.save(filepath)
        
        # Create thumbnail
        thumbnail_path = os.path.join(THUMBNAILS_FOLDER, f"thumb_{filename}")
        create_thumbnail(filepath, thumbnail_path)
        
        flash('File uploaded successfully!', 'success')
        return redirect(url_for('index'))
    
    flash('Invalid file type', 'error')
    return redirect(url_for('index'))

@app.route('/display/<filename>')
def display_image(filename):
    """Display an image on the e-ink screen."""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(image_path):
        flash('Image not found', 'error')
        return redirect(url_for('index'))
    
    # Get saturation parameter
    saturation = float(request.args.get('saturation', 0.5))
    
    # Display the image in a background thread
    def display_task():
        success, message = display_image_on_eink(image_path, saturation)
        if not success:
            print(f"Display error: {message}")
    
    thread = threading.Thread(target=display_task)
    thread.start()
    
    flash('Displaying image on e-ink screen...', 'info')
    return redirect(url_for('index'))

@app.route('/delete/<filename>')
def delete_image(filename):
    """Delete an uploaded image."""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    thumbnail_path = os.path.join(THUMBNAILS_FOLDER, f"thumb_{filename}")
    
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        flash('Image deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting image: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/thumbnail/<filename>')
def serve_thumbnail(filename):
    """Serve thumbnail images."""
    return send_from_directory(THUMBNAILS_FOLDER, filename)

if __name__ == '__main__':
    # Create the HTML template
    template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkyRemote</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background-color: #2c3e50;
            color: white;
            padding: 2rem 0;
            margin-bottom: 2rem;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        
        h1 {
            text-align: center;
            font-size: 2.5rem;
            font-weight: 300;
        }
        
        .status {
            text-align: center;
            margin-top: 1rem;
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .upload-section {
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .upload-form {
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }
        
        input[type="file"] {
            flex: 1;
            padding: 0.5rem;
            border: 2px dashed #3498db;
            border-radius: 4px;
            background: #f8f9fa;
        }
        
        button {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 0.75rem 1.5rem;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.3s;
        }
        
        button:hover {
            background-color: #2980b9;
        }
        
        .flash-messages {
            margin-bottom: 1rem;
        }
        
        .flash {
            padding: 1rem;
            border-radius: 4px;
            margin-bottom: 0.5rem;
        }
        
        .flash.success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .flash.error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .flash.info {
            background-color: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .image-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 1.5rem;
        }
        
        .image-card {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s, box-shadow 0.3s;
        }
        
        .image-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 20px rgba(0,0,0,0.15);
        }
        
        .image-preview {
            width: 100%;
            height: 200px;
            object-fit: cover;
            background-color: #f0f0f0;
        }
        
        .image-info {
            padding: 1rem;
        }
        
        .image-filename {
            font-weight: bold;
            margin-bottom: 0.5rem;
            word-break: break-all;
        }
        
        .image-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        
        .btn-display {
            background-color: #27ae60;
            flex: 1;
        }
        
        .btn-display:hover {
            background-color: #229954;
        }
        
        .btn-delete {
            background-color: #e74c3c;
        }
        
        .btn-delete:hover {
            background-color: #c0392b;
        }
        
        .current-image {
            border: 3px solid #27ae60;
        }
        
        .saturation-control {
            margin: 0.5rem 0;
        }
        
        .saturation-control label {
            display: block;
            font-size: 0.9rem;
            margin-bottom: 0.25rem;
        }
        
        .saturation-control input[type="range"] {
            width: 100%;
        }
        
        .saturation-value {
            font-size: 0.8rem;
            text-align: right;
            color: #666;
        }
        
        @media (max-width: 768px) {
            .image-grid {
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            }
            
            h1 {
                font-size: 2rem;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>InkyRemote</h1>
            {% if current_image %}
            <div class="status">Currently displaying: {{ current_image }}</div>
            {% endif %}
        </div>
    </header>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash {{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        <div class="upload-section">
            <h2>Upload New Image</h2>
            <form method="POST" action="{{ url_for('upload_file') }}" enctype="multipart/form-data" class="upload-form">
                <input type="file" name="file" accept="image/*" required>
                <button type="submit">Upload</button>
            </form>
        </div>
        
        <h2 style="margin-bottom: 1rem;">Image Gallery</h2>
        <div class="image-grid">
            {% for image in images %}
            <div class="image-card {% if image.filename == current_image %}current-image{% endif %}">
                <img src="{{ url_for('serve_thumbnail', filename='thumb_' + image.filename) }}" 
                     alt="{{ image.filename }}" 
                     class="image-preview">
                <div class="image-info">
                    <div class="image-filename">{{ image.filename }}</div>
                    
                    <div class="saturation-control">
                        <label for="saturation-{{ loop.index }}">Saturation:</label>
                        <input type="range" id="saturation-{{ loop.index }}" 
                               min="0" max="1" step="0.1" value="0.5"
                               onchange="updateSaturationValue({{ loop.index }}, this.value)">
                        <div class="saturation-value" id="saturation-value-{{ loop.index }}">0.5</div>
                    </div>
                    
                    <div class="image-actions">
                        <button class="btn-display" onclick="displayImage('{{ image.filename }}', {{ loop.index }})">
                            Display
                        </button>
                        <button class="btn-delete" onclick="if(confirm('Delete this image?')) window.location.href='{{ url_for('delete_image', filename=image.filename) }}'">
                            Delete
                        </button>
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>
        
        {% if not images %}
        <p style="text-align: center; margin-top: 2rem; color: #666;">No images uploaded yet. Upload an image to get started!</p>
        {% endif %}
    </div>
    
    <script>
        function updateSaturationValue(index, value) {
            document.getElementById('saturation-value-' + index).textContent = value;
        }
        
        function displayImage(filename, index) {
            const saturation = document.getElementById('saturation-' + index).value;
            window.location.href = "{{ url_for('display_image', filename='FILENAME') }}".replace('FILENAME', filename) + '?saturation=' + saturation;
        }
    </script>
</body>
</html>'''
    
    template_path = os.path.join('templates', 'index.html')
    # Always write the template to ensure it's up to date with code changes
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    print("InkyRemote starting...")
    print("Open your browser and go to http://localhost:5000")
    print("Or from another device: http://[your-pi-ip]:5000")
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True)