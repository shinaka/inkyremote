#!/usr/bin/env python3

import os
import uuid
import json
import time
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import threading

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

def create_thumbnail(image_path, thumbnail_path, size=(200, 150)):
    """Create a thumbnail of the uploaded image."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for PNG with transparency, etc.)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            img.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Ensure the thumbnail directory exists
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            
            img.save(thumbnail_path, 'JPEG', quality=85)
            print(f"Thumbnail created: {thumbnail_path}")
        return True
    except Exception as e:
        print(f"Error creating thumbnail for {image_path}: {e}")
        return False

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
    """Handle file upload with cropping support."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file selected'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'})
    
    if file:
        try:
            # Generate unique filename
            timestamp = int(time.time())
            original_filename = secure_filename(file.filename)
            name, ext = os.path.splitext(original_filename)
            
            # If it's from the cropper, it will be a .jpg
            if file.filename == 'cropped_image.jpg':
                filename = f"cropped_{timestamp}.jpg"
            else:
                filename = f"{name}_{timestamp}{ext}"
            
            # Save the file
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Create thumbnail
            thumbnail_path = os.path.join(THUMBNAILS_FOLDER, f"thumb_{filename}")
            create_thumbnail(file_path, thumbnail_path)
            
            print(f"File uploaded successfully: {filename}")
            return jsonify({'success': True, 'message': f'Image uploaded successfully as {filename}'})
            
        except Exception as e:
            print(f"Upload error: {str(e)}")
            return jsonify({'success': False, 'message': f'Upload failed: {str(e)}'})
    
    return jsonify({'success': False, 'message': 'Invalid file type'})

@app.route('/display/<filename>')
def display_image(filename):
    """Display an image on the e-ink screen."""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(image_path):
        return jsonify({'success': False, 'message': 'Image not found'})
    
    # Get saturation from query parameter (default: 0.5)
    saturation = float(request.args.get('saturation', 0.5))
    
    # Display the image in a separate thread to avoid blocking
    def display_thread():
        success, message = display_image_on_eink(image_path, saturation)
        if success:
            print(f"Successfully displayed: {filename}")
        else:
            print(f"Display error: {message}")
    
    thread = threading.Thread(target=display_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': f'Displaying {filename} on e-ink screen'})

@app.route('/delete/<filename>')
def delete_image(filename):
    """Delete an image and its thumbnail."""
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    thumbnail_path = os.path.join(THUMBNAILS_FOLDER, f"thumb_{filename}")
    
    try:
        # Delete the main image
        if os.path.exists(image_path):
            os.remove(image_path)
            print(f"Deleted image: {filename}")
        
        # Delete the thumbnail
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            print(f"Deleted thumbnail: thumb_{filename}")
        
        # Clear current display if this was the displayed image
        global current_display_image
        if current_display_image == filename:
            current_display_image = None
        
        flash(f'Image {filename} deleted successfully')
        
    except Exception as e:
        flash(f'Error deleting image: {str(e)}')
        print(f"Delete error: {str(e)}")
    
    return redirect(url_for('index'))

@app.route('/thumbnails/<filename>')
def serve_thumbnail(filename):
    """Serve thumbnail images."""
    return send_from_directory(THUMBNAILS_FOLDER, filename)

@app.route('/uploads/<filename>')
def serve_upload(filename):
    """Serve uploaded images."""
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/status')
def status():
    """Get current display status."""
    return jsonify({
        'current_image': current_display_image,
        'total_images': len(get_image_list())
    })

@app.route('/clear')
def clear_display():
    """Clear the e-ink display."""
    global current_display_image
    
    def clear_thread():
        with display_lock:
            try:
                inky = auto(ask_user=False, verbose=True)
                # Create a white image to clear the display
                clear_image = Image.new('RGB', inky.resolution, 'white')
                inky.set_image(clear_image)
                inky.show()
                current_display_image = None
                print("Display cleared")
            except Exception as e:
                print(f"Error clearing display: {str(e)}")
    
    thread = threading.Thread(target=clear_thread)
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'Display cleared'})

# Create a basic HTML template if it doesn't exist
def create_basic_template():
    """Create a basic HTML template for the app."""
    template_content = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-Ink Remote Display</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.12/cropper.min.css">
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .status {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .upload-section {
            background: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .crop-wrapper {
            max-width: 100%;
            margin: 20px 0;
        }
        .crop-controls {
            margin-top: 15px;
            text-align: center;
        }
        .crop-controls button {
            margin: 0 10px;
        }
        .file-input {
            margin-bottom: 10px;
        }
        .btn {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
        .btn:hover {
            background-color: #0056b3;
        }
        .btn-secondary {
            background-color: #6c757d;
            border-color: #6c757d;
        }
        .btn-secondary:hover {
            background-color: #5a6268;
            border-color: #545b62;
        }
        .btn-danger {
            background-color: #dc3545;
        }
        .btn-danger:hover {
            background-color: #c82333;
        }
        .images-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .image-card {
            background: white;
            border-radius: 5px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            text-align: center;
        }
        .image-card img {
            max-width: 100%;
            height: auto;
            border-radius: 3px;
        }
        .image-card h3 {
            margin: 10px 0;
            font-size: 14px;
            word-break: break-all;
        }
        .image-actions {
            margin-top: 10px;
        }
        .image-actions a {
            margin: 0 5px;
        }
        .current-display {
            border: 3px solid #28a745;
        }
        .saturation-control {
            margin: 10px 0;
        }
        .saturation-control input {
            width: 100px;
        }
        .alerts {
            margin-bottom: 20px;
        }
        .alert {
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 4px;
        }
        .alert-success {
            background-color: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-error {
            background-color: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>E-Ink Remote Display</h1>
        <p>Upload and display images on your e-ink screen (800x480)</p>
    </div>

    <div class="alerts">
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                {% for message in messages %}
                    <div class="alert alert-success">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
    </div>

    <div class="status">
        <strong>Current Display:</strong> 
        {% if current_image %}
            {{ current_image }}
            <a href="{{ url_for('clear_display') }}" class="btn btn-secondary" style="margin-left: 10px;">Clear Display</a>
        {% else %}
            None
        {% endif %}
    </div>

    <div class="upload-section">
        <h2>Upload New Image</h2>
        
        <!-- Step 1: File selection -->
        <div id="file-selection">
            <form class="upload-form">
                <input type="file" id="file-input" class="file-input" accept="image/*" required>
                <p><small>Supported formats: PNG, JPG, JPEG, GIF, BMP, TIFF (Max size: 16MB)</small></p>
            </form>
        </div>
        
        <!-- Step 2: Cropping interface -->
        <div id="crop-container" style="display: none;">
            <h3>Crop your image for e-ink display (800x480)</h3>
            <div class="crop-wrapper">
                <img id="crop-image" style="max-width: 100%; max-height: 400px;">
            </div>
            <div class="crop-controls">
                <button type="button" id="crop-upload-btn" class="btn">Crop & Upload</button>
                <button type="button" id="cancel-crop-btn" class="btn btn-secondary">Cancel</button>
            </div>
        </div>
    </div>

    <div class="images-grid">
        {% for image in images %}
            <div class="image-card {% if image.filename == current_image %}current-display{% endif %}">
                <img src="{{ url_for('serve_thumbnail', filename='thumb_' + image.filename) }}" alt="{{ image.filename }}">
                <h3>{{ image.filename }}</h3>
                <div class="saturation-control">
                    <label for="saturation-{{ loop.index }}">Saturation:</label>
                    <input type="range" id="saturation-{{ loop.index }}" min="0" max="1" step="0.1" value="0.5">
                </div>
                <div class="image-actions">
                    <a href="#" onclick="displayImage('{{ image.filename }}', document.getElementById('saturation-{{ loop.index }}').value)" class="btn">Display</a>
                    <a href="{{ url_for('delete_image', filename=image.filename) }}" class="btn btn-danger" onclick="return confirm('Are you sure you want to delete this image?')">Delete</a>
                </div>
            </div>
        {% endfor %}
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.12/cropper.min.js"></script>
    <script>
        let cropper = null;

        document.getElementById('file-input').addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    showCropInterface(e.target.result);
                };
                reader.readAsDataURL(file);
            }
        });

        function showCropInterface(imageSrc) {
            // Hide file selection, show crop interface
            document.getElementById('file-selection').style.display = 'none';
            document.getElementById('crop-container').style.display = 'block';
            
            // Set image source
            const cropImage = document.getElementById('crop-image');
            cropImage.src = imageSrc;
            
            // Initialize cropper with e-ink display aspect ratio (800:480 = 5:3)
            cropper = new Cropper(cropImage, {
                aspectRatio: 800 / 480, // 5:3 ratio
                viewMode: 1,
                dragMode: 'move',
                autoCropArea: 1,
                restore: false,
                guides: true,
                center: true,
                highlight: false,
                cropBoxMovable: true,
                cropBoxResizable: true,
                toggleDragModeOnDblclick: false,
            });
        }

        document.getElementById('crop-upload-btn').addEventListener('click', function() {
            if (cropper) {
                // Get cropped canvas
                const canvas = cropper.getCroppedCanvas({
                    width: 800,
                    height: 480,
                    imageSmoothingEnabled: true,
                    imageSmoothingQuality: 'high'
                });
                
                // Convert to blob and upload
                canvas.toBlob(function(blob) {
                    uploadCroppedImage(blob);
                }, 'image/jpeg', 0.9);
            }
        });

        document.getElementById('cancel-crop-btn').addEventListener('click', function() {
            cancelCrop();
        });

        function uploadCroppedImage(blob) {
            const formData = new FormData();
            formData.append('file', blob, 'cropped_image.jpg');
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    location.reload(); // Reload to show the uploaded image
                } else {
                    alert('Upload failed: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Upload failed');
            });
        }

        function cancelCrop() {
            if (cropper) {
                cropper.destroy();
                cropper = null;
            }
            document.getElementById('crop-container').style.display = 'none';
            document.getElementById('file-selection').style.display = 'block';
            document.getElementById('file-input').value = '';
        }

        function displayImage(filename, saturation) {
            fetch(`/display/${filename}?saturation=${saturation}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(data.message);
                        setTimeout(() => location.reload(), 1000);
                    } else {
                        alert('Display failed: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Display failed');
                });
        }
    </script>
</body>
</html>'''
    
    template_path = 'templates/index.html'
    if not os.path.exists(template_path):
        with open(template_path, 'w') as f:
            f.write(template_content)
        print(f"Created template: {template_path}")

if __name__ == '__main__':
    create_basic_template()
    print("Starting E-Ink Remote Display server...")
    print("Upload images and display them on your e-ink screen!")
    print("Access the web interface at: http://localhost:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000)