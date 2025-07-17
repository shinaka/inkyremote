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

def crop_image(image_path, crop_data):
    """Crop image based on crop coordinates and resize to display resolution."""
    try:
        with Image.open(image_path) as img:
            # Apply rotation if specified
            if 'rotate' in crop_data and crop_data['rotate'] != 0:
                img = img.rotate(-crop_data['rotate'], expand=True)
            
            # Extract crop coordinates
            x = int(crop_data['x'])
            y = int(crop_data['y'])
            width = int(crop_data['width'])
            height = int(crop_data['height'])
            
            # Crop the image
            cropped = img.crop((x, y, x + width, y + height))
            
            # Resize to exact display resolution (800x480)
            resized = cropped.resize((800, 480), Image.Resampling.LANCZOS)
            
            return resized
    except Exception as e:
        print(f"Error cropping image: {e}")
        return None

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
    """Upload and optionally crop an image."""
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        # Generate unique filename
        filename = str(uuid.uuid4()) + '.' + file.filename.rsplit('.', 1)[1].lower()
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the uploaded file
        file.save(filepath)
        
        # Check if crop data is provided
        crop_data = request.form.get('crop_data')
        if crop_data:
            try:
                crop_info = json.loads(crop_data)
                cropped_image = crop_image(filepath, crop_info)
                if cropped_image:
                    cropped_image.save(filepath)
                    flash('Image uploaded and cropped successfully!', 'success')
                else:
                    flash('Image uploaded but cropping failed', 'warning')
            except json.JSONDecodeError:
                flash('Invalid crop data, image uploaded without cropping', 'warning')
        else:
            flash('Image uploaded successfully!', 'success')
        
        return redirect(url_for('index'))
    else:
        flash('Invalid file type. Please upload an image file.', 'error')
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
    """Delete an uploaded image and its thumbnail."""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    thumbnail_path = os.path.join(app.config['THUMBNAILS_FOLDER'], f"thumb_{filename}")
    
    try:
        if os.path.exists(image_path):
            os.remove(image_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        flash('Image deleted successfully', 'success')
    except Exception as e:
        flash(f'Error deleting image: {str(e)}', 'error')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Create the HTML template
    template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>InkyRemote</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css">
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
            flex-direction: column;
            gap: 1rem;
        }
        
        .file-input-container {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .file-input {
            flex: 1;
            padding: 0.8rem;
            border: 2px dashed #ddd;
            border-radius: 4px;
            background: #f9f9f9;
            cursor: pointer;
            transition: border-color 0.2s;
        }
        
        .file-input:hover {
            border-color: #3498db;
        }
        
        .btn {
            padding: 0.8rem 1.5rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.2s;
        }
        
        .btn-primary {
            background-color: #3498db;
            color: white;
        }
        
        .btn-primary:hover {
            background-color: #2980b9;
        }
        
        .btn-success {
            background-color: #27ae60;
            color: white;
        }
        
        .btn-success:hover {
            background-color: #229954;
        }
        
        .btn-danger {
            background-color: #e74c3c;
            color: white;
        }
        
        .btn-danger:hover {
            background-color: #c0392b;
        }
        
        .btn-secondary {
            background-color: #95a5a6;
            color: white;
        }
        
        .btn-secondary:hover {
            background-color: #7f8c8d;
        }
        
        .btn-rotate {
            background-color: #9b59b6;
            color: white;
            padding: 0.5rem 0.8rem;
            font-size: 1.2rem;
            min-width: 40px;
        }
        
        .btn-rotate:hover {
            background-color: #8e44ad;
        }
        
        .crop-container {
            display: none;
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .crop-preview {
            max-width: 100%;
            max-height: 400px;
            margin-bottom: 1rem;
        }
        
        .crop-controls {
            display: flex;
            gap: 1rem;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .rotation-controls {
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }
        
        .rotation-label {
            font-weight: 500;
            color: #666;
        }
        
        .crop-info {
            text-align: center;
            margin-bottom: 1rem;
            color: #666;
        }
        
        .images-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-top: 2rem;
        }
        
        .image-card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
            transition: transform 0.2s;
        }
        
        .image-card:hover {
            transform: translateY(-2px);
        }
        
        .image-preview {
            width: 100%;
            height: 200px;
            object-fit: cover;
        }
        
        .image-info {
            padding: 1rem;
        }
        
        .image-name {
            font-weight: 600;
            margin-bottom: 0.5rem;
            word-break: break-all;
        }
        
        .image-controls {
            display: flex;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        
        .saturation-control {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }
        
        .saturation-slider {
            flex: 1;
        }
        
        .btn-display {
            background-color: #3498db;
            color: white;
        }
        
        .btn-display:hover {
            background-color: #2980b9;
        }
        
        .btn-delete {
            background-color: #e74c3c;
            color: white;
        }
        
        .btn-delete:hover {
            background-color: #c0392b;
        }
        
        .flash-messages {
            margin-bottom: 1rem;
        }
        
        .flash-message {
            padding: 0.75rem 1rem;
            margin-bottom: 0.5rem;
            border-radius: 4px;
            font-weight: 500;
        }
        
        .flash-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .flash-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .flash-warning {
            background-color: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
        }
        
        .flash-info {
            background-color: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        
        .current-image {
            border: 3px solid #27ae60;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>InkyRemote</h1>
            <div class="status">
                {% if current_image %}
                    Currently displaying: {{ current_image }}
                {% else %}
                    No image currently displayed
                {% endif %}
            </div>
        </div>
    </header>
    
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <div class="flash-messages">
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        <div class="upload-section">
            <h2>Upload New Image</h2>
            <form class="upload-form" method="post" action="{{ url_for('upload_file') }}" enctype="multipart/form-data" id="upload-form">
                <div class="file-input-container">
                    <input type="file" name="file" class="file-input" accept="image/*" id="file-input" required>
                    <button type="submit" class="btn btn-primary" id="upload-btn">Upload</button>
                </div>
                <input type="hidden" name="crop_data" id="crop-data">
            </form>
        </div>
        
        <div class="crop-container" id="crop-container">
            <div class="crop-info">
                <p>Crop and rotate your image to fit the 800x480 e-ink display (5:3 aspect ratio)</p>
            </div>
            <div>
                <img id="crop-image" class="crop-preview">
            </div>
            <div class="crop-controls">
                <div class="rotation-controls">
                    <span class="rotation-label">Rotate:</span>
                    <button type="button" class="btn btn-rotate" id="rotate-left" title="Rotate left">↺</button>
                    <button type="button" class="btn btn-rotate" id="rotate-right" title="Rotate right">↻</button>
                </div>
                <button type="button" class="btn btn-success" id="crop-and-upload">Crop & Upload</button>
                <button type="button" class="btn btn-secondary" id="cancel-crop">Cancel</button>
            </div>
        </div>
        
        <div class="images-grid">
            {% for image in images %}
            <div class="image-card {% if image.filename == current_image %}current-image{% endif %}">
                <div class="image-preview-container">
                    <img src="{{ url_for('static', filename='thumbnails/thumb_' + image.filename) }}" 
                         alt="{{ image.filename }}" 
                         class="image-preview"
                         onerror="this.src='{{ url_for('static', filename='uploads/' + image.filename) }}'">
                </div>
                <div class="image-info">
                    <div class="image-name">{{ image.filename }}</div>
                    <div class="saturation-control">
                        <label for="saturation-{{ loop.index0 }}">Saturation:</label>
                        <input type="range" id="saturation-{{ loop.index0 }}" class="saturation-slider" 
                               min="0" max="1" step="0.1" value="0.5" 
                               oninput="updateSaturationValue({{ loop.index0 }}, this.value)">
                        <span id="saturation-value-{{ loop.index0 }}">0.5</span>
                    </div>
                    <div class="image-controls">
                        <button class="btn btn-display" onclick="displayImage('{{ image.filename }}', {{ loop.index0 }})">
                            Display
                        </button>
                        <button class="btn btn-delete" onclick="if(confirm('Delete this image?')) window.location.href='{{ url_for('delete_image', filename=image.filename) }}'">
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
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>
    <script>
        let cropper;
        let originalFile;
        let currentRotation = 0;
        
        function updateSaturationValue(index, value) {
            document.getElementById('saturation-value-' + index).textContent = value;
        }
        
        function displayImage(filename, index) {
            const saturation = document.getElementById('saturation-' + index).value;
            window.location.href = "{{ url_for('display_image', filename='FILENAME') }}".replace('FILENAME', filename) + '?saturation=' + saturation;
        }
        
        // Handle file selection
        document.getElementById('file-input').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                originalFile = file;
                currentRotation = 0;
                const reader = new FileReader();
                reader.onload = function(e) {
                    const cropImage = document.getElementById('crop-image');
                    cropImage.src = e.target.result;
                    
                    // Show crop container and hide upload button
                    document.getElementById('crop-container').style.display = 'block';
                    document.getElementById('upload-btn').style.display = 'none';
                    
                    // Initialize cropper with 5:3 aspect ratio (800:480)
                    if (cropper) {
                        cropper.destroy();
                    }
                    
                    cropper = new Cropper(cropImage, {
                        aspectRatio: 800 / 480,
                        viewMode: 1,
                        responsive: true,
                        autoCropArea: 1,
                        guides: true,
                        center: true,
                        highlight: false,
                        cropBoxMovable: true,
                        cropBoxResizable: true,
                        toggleDragModeOnDblclick: false,
                        rotatable: true,
                        scalable: true,
                        zoomable: true,
                    });
                };
                reader.readAsDataURL(file);
            }
        });
        
        // Rotation controls
        document.getElementById('rotate-left').addEventListener('click', function() {
            if (cropper) {
                cropper.rotate(-90);
                currentRotation -= 90;
            }
        });
        
        document.getElementById('rotate-right').addEventListener('click', function() {
            if (cropper) {
                cropper.rotate(90);
                currentRotation += 90;
            }
        });
        
        // Handle crop and upload
        document.getElementById('crop-and-upload').addEventListener('click', function() {
            if (cropper) {
                const cropData = cropper.getData();
                // Add rotation data
                cropData.rotate = currentRotation;
                document.getElementById('crop-data').value = JSON.stringify(cropData);
                document.getElementById('upload-form').submit();
            }
        });
        
        // Handle cancel crop
        document.getElementById('cancel-crop').addEventListener('click', function() {
            if (cropper) {
                cropper.destroy();
                cropper = null;
            }
            currentRotation = 0;
            document.getElementById('crop-container').style.display = 'none';
            document.getElementById('upload-btn').style.display = 'block';
            document.getElementById('file-input').value = '';
            document.getElementById('crop-data').value = '';
        });
        
        // Prevent form submission when cropping is active
        document.getElementById('upload-form').addEventListener('submit', function(e) {
            if (cropper && !document.getElementById('crop-data').value) {
                e.preventDefault();
            }
        });
    </script>
</body>
</html>'''
    
    template_path = os.path.join('templates', 'index.html')
    # Always write the template to ensure it's up to date with code changes
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    print("InkyRemote starting...")
    print("Open your browser and go to http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)