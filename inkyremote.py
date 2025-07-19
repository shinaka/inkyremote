#!/usr/bin/env python3

import os
import sys
import uuid
import json
import atexit
from flask import Flask, request, render_template, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import threading
import time
import logging

# Import the Inky library
from inky.auto import auto

# Import our network management modules
from network_manager import network_manager, NetworkStatus, NetworkMode
from button_handler import button_handler, ButtonAction
from display_manager import display_manager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = 'your-secret-key-change-this'  # Change this to a random secret key

# Configuration
UPLOAD_FOLDER = 'static/uploads'
THUMBNAILS_FOLDER = 'static/thumbnails'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['THUMBNAILS_FOLDER'] = THUMBNAILS_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(THUMBNAILS_FOLDER, exist_ok=True)
os.makedirs('templates', exist_ok=True)

# Global variable to track current display
current_display_image = None
display_lock = threading.Lock()

# Network management state
network_status = NetworkStatus(mode=NetworkMode.UNKNOWN)
last_network_mode = NetworkMode.UNKNOWN

# Initialize network components on app startup
def initialize_network_management():
    """Initialize all network management components."""
    logger.info("Initializing network management...")
    
    # Initialize display manager
    if not display_manager.initialize_display():
        logger.warning("Display manager initialization failed - continuing without display updates")
    
    # Initialize button handler
    if not button_handler.initialize():
        logger.warning("Button handler initialization failed - continuing without button support")
    else:
        # Set up button callbacks
        setup_button_callbacks()
        button_handler.start_monitoring()
    
    # Initialize network manager
    if not network_manager.initialize():
        logger.error("Network manager initialization failed!")
        return False
    
    # Set up network status callback
    network_manager.add_status_callback(on_network_status_change)
    
    # Start network monitoring
    network_manager.start_monitoring()
    
    logger.info("Network management initialized successfully")
    return True

def setup_button_callbacks():
    """Set up callbacks for button presses."""
    
    def on_network_toggle(button_label: str):
        logger.info(f"Button {button_label}: Toggling network mode")
        success = network_manager.toggle_mode()
        if success:
            display_manager.show_message(
                "Network Toggle", 
                "Switching network mode...", 
                "info", 
                duration=3.0
            )
        else:
            display_manager.show_message(
                "Network Error", 
                "Failed to toggle network mode", 
                "error", 
                duration=5.0
            )
    
    def on_status_display(button_label: str):
        logger.info(f"Button {button_label}: Showing network status")
        status = network_manager.get_current_status()
        display_manager.show_network_status(status)
    
    def on_wifi_mode(button_label: str):
        logger.info(f"Button {button_label}: Forcing WiFi mode")
        success = network_manager.switch_to_wifi_mode(manual=True)
        if success:
            display_manager.show_message(
                "WiFi Mode", 
                "Switching to WiFi mode...", 
                "info", 
                duration=3.0
            )
        else:
            display_manager.show_message(
                "WiFi Error", 
                "Failed to switch to WiFi mode", 
                "error", 
                duration=5.0
            )
    
    def on_ap_mode(button_label: str):
        logger.info(f"Button {button_label}: Forcing AP mode")
        success = network_manager.switch_to_ap_mode(manual=True)
        if success:
            display_manager.show_message(
                "AP Mode", 
                "Switching to Access Point mode...", 
                "info", 
                duration=3.0
            )
        else:
            display_manager.show_message(
                "AP Error", 
                "Failed to switch to AP mode", 
                "error", 
                duration=5.0
            )
    
    # Register button callbacks
    button_handler.add_button_callback(ButtonAction.NETWORK_TOGGLE, on_network_toggle)
    button_handler.add_button_callback(ButtonAction.STATUS_DISPLAY, on_status_display)
    button_handler.add_button_callback(ButtonAction.WIFI_MODE, on_wifi_mode)
    button_handler.add_button_callback(ButtonAction.AP_MODE, on_ap_mode)

def on_network_status_change(status: NetworkStatus):
    """Callback for network status changes."""
    global network_status, last_network_mode
    
    logger.info(f"Network status changed: {status.mode.value}")
    
    # Check if mode actually changed
    if status.mode != last_network_mode and last_network_mode != NetworkMode.UNKNOWN:
        logger.info(f"Network mode changed from {last_network_mode.value} to {status.mode.value}")
        display_manager.show_connection_change(last_network_mode, status.mode)
    
    # Update global state
    network_status = status
    last_network_mode = status.mode

def cleanup_network_management():
    """Clean up network management components."""
    logger.info("Cleaning up network management...")
    
    try:
        network_manager.stop_monitoring()
        button_handler.cleanup()
        
        # Clean up PID file
        pidfile = '/tmp/inkyremote.pid'
        if os.path.exists(pidfile):
            os.remove(pidfile)
            
        logger.info("Network management cleanup completed")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

# Register cleanup function
atexit.register(cleanup_network_management)

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
    """Display an image on the e-ink display using the unified DisplayManager."""
    global current_display_image
    
    with display_lock:
        try:
            # Try to use the DisplayManager first (unified approach)
            success = display_manager.display_image(image_path, saturation)
            
            if success:
                current_display_image = os.path.basename(image_path)
                return True, "Image displayed successfully"
            else:
                # Fallback to direct display if DisplayManager fails
                logger.warning("DisplayManager failed, trying direct display...")
                
                # Initialize the display directly as fallback
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
                return True, "Image displayed successfully (fallback mode)"
                
        except Exception as e:
            return False, f"Error displaying image: {str(e)}"

@app.route('/')
def index():
    """Main page showing all uploaded images."""
    images = get_image_list()
    
    # Get current network status for display
    try:
        current_network_status = network_manager.get_current_status()
    except Exception as e:
        logger.warning(f"Could not get network status: {e}")
        current_network_status = NetworkStatus(mode=NetworkMode.UNKNOWN)
    
    return render_template('index.html', 
                         images=images, 
                         current_image=current_display_image,
                         network_status=current_network_status)

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

@app.route('/api/network/status')
def api_network_status():
    """API endpoint to get current network status."""
    try:
        status = network_manager.get_current_status()
        return jsonify({
            'mode': status.mode.value,
            'ssid': status.ssid,
            'ip_address': status.ip_address,
            'connected_clients': status.connected_clients,
            'signal_strength': status.signal_strength,
            'is_internet_available': status.is_internet_available,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/network/toggle', methods=['POST'])
def api_network_toggle():
    """API endpoint to toggle network mode."""
    try:
        success = network_manager.toggle_mode()
        if success:
            return jsonify({'success': True, 'message': 'Network mode toggle initiated'})
        else:
            return jsonify({'success': False, 'message': 'Failed to toggle network mode'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/network/wifi', methods=['POST'])
def api_switch_to_wifi():
    """API endpoint to switch to WiFi mode."""
    try:
        success = network_manager.switch_to_wifi_mode(manual=True)
        if success:
            return jsonify({'success': True, 'message': 'Switching to WiFi mode'})
        else:
            return jsonify({'success': False, 'message': 'Failed to switch to WiFi mode'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/network/ap', methods=['POST'])
def api_switch_to_ap():
    """API endpoint to switch to AP mode."""
    try:
        success = network_manager.switch_to_ap_mode(manual=True)
        if success:
            return jsonify({'success': True, 'message': 'Switching to AP mode'})
        else:
            return jsonify({'success': False, 'message': 'Failed to switch to AP mode'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/network/status')
def network_status_page():
    """Show network status on E-Ink display and web page."""
    try:
        status = network_manager.get_current_status()
        
        # Show on E-Ink display
        display_manager.show_network_status(status)
        
        flash('Network status displayed on E-Ink screen', 'info')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error displaying network status: {str(e)}', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    # Check for existing instances using simple PID file
    pidfile = '/tmp/inkyremote.pid'
    if os.path.exists(pidfile):
        try:
            with open(pidfile, 'r') as f:
                old_pid = int(f.read().strip())
            
            # Check if process still exists
            try:
                os.kill(old_pid, 0)  # Signal 0 just checks if process exists
                logger.error(f"InkyRemote already running (PID: {old_pid}). Exiting to prevent conflicts.")
                logger.error("Stop existing instances first: sudo systemctl stop inkyremote.service")
                sys.exit(1)
            except OSError:
                # Process doesn't exist, remove stale PID file
                os.remove(pidfile)
        except (ValueError, IOError):
            # Bad PID file, remove it
            os.remove(pidfile)
    
    # Write our PID
    with open(pidfile, 'w') as f:
        f.write(str(os.getpid()))
    
    # Initialize network management
    logger.info("Starting InkyRemote with network management...")
    if not initialize_network_management():
        logger.error("Failed to initialize network management - starting without network features")
    
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
        
        .btn-zoom {
            background-color: #34495e;
            color: white;
            padding: 0.5rem 0.8rem;
            font-size: 1rem;
            min-width: 40px;
        }
        
        .btn-zoom:hover {
            background-color: #2c3e50;
        }
        
        .crop-container {
            display: none;
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .crop-preview-container {
            width: 100%;
            height: 500px;
            margin-bottom: 1rem;
            overflow: hidden;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        
        .crop-preview {
            max-width: 100%;
            max-height: 100%;
        }
        
        .crop-controls {
            display: flex;
            gap: 1rem;
            justify-content: center;
            align-items: center;
            flex-wrap: wrap;
        }
        
        .rotation-controls, .zoom-controls {
            display: flex;
            gap: 0.5rem;
            align-items: center;
        }
        
        .control-label {
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
                
                {% if network_status %}
                    <br>
                    Network: 
                    {% if network_status.mode.value == 'wifi' %}
                        📶 WiFi ({{ network_status.ssid or 'Unknown' }})
                        {% if network_status.ip_address %} - {{ network_status.ip_address }}{% endif %}
                    {% elif network_status.mode.value == 'access_point' %}
                        📡 Access Point ({{ network_status.ssid }})
                        {% if network_status.connected_clients > 0 %} - {{ network_status.connected_clients }} connected{% endif %}
                    {% elif network_status.mode.value == 'transitioning' %}
                        🔄 Switching modes...
                    {% else %}
                        ❓ Unknown status
                    {% endif %}
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
        
        <div class="upload-section">
            <h2>Network Controls</h2>
            <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; margin-bottom: 1rem;">
                <button class="btn btn-primary" onclick="showNetworkStatus()">Show Network Status</button>
                <button class="btn btn-secondary" onclick="toggleNetworkMode()">Toggle WiFi/AP Mode</button>
                <button class="btn btn-success" onclick="switchToWiFi()">Force WiFi Mode</button>
                <button class="btn" style="background-color: #3498db; color: white;" onclick="switchToAP()">Force AP Mode</button>
            </div>
            <div style="text-align: center; font-size: 0.9rem; color: #666;">
                <p><strong>Physical Button Controls:</strong></p>
                <p>Button A: Toggle WiFi/AP • Button B: Show Status • Hold C: WiFi • Hold D: AP</p>
            </div>
        </div>
        
        <div class="crop-container" id="crop-container">
            <div class="crop-info">
                <p>Crop and rotate your image to fit the 800x480 e-ink display (5:3 aspect ratio)</p>
            </div>
            <div class="crop-preview-container">
                <img id="crop-image" class="crop-preview">
            </div>
            <div class="crop-controls">
                <div class="rotation-controls">
                    <span class="control-label">Rotate:</span>
                    <button type="button" class="btn btn-rotate" id="rotate-left" title="Rotate left">↺</button>
                    <button type="button" class="btn btn-rotate" id="rotate-right" title="Rotate right">↻</button>
                </div>
                <div class="zoom-controls">
                    <span class="control-label">Zoom:</span>
                    <button type="button" class="btn btn-zoom" id="zoom-in" title="Zoom in">+</button>
                    <button type="button" class="btn btn-zoom" id="zoom-out" title="Zoom out">-</button>
                    <button type="button" class="btn btn-zoom" id="reset-zoom" title="Reset zoom">⌂</button>
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
        
        function resetCropperView() {
            if (cropper) {
                cropper.reset();
                cropper.zoom(0);
            }
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
                        viewMode: 0,  // Changed from 1 to 0 for more flexibility
                        responsive: true,
                        autoCropArea: 0.8,  // Reduced from 1 to 0.8
                        guides: true,
                        center: true,
                        highlight: false,
                        cropBoxMovable: true,
                        cropBoxResizable: true,
                        toggleDragModeOnDblclick: false,
                        rotatable: true,
                        scalable: true,
                        zoomable: true,
                        minContainerWidth: 200,
                        minContainerHeight: 100,
                        checkCrossOrigin: false,
                        zoomOnTouch: false,
                        zoomOnWheel: false,
                        wheelZoomRatio: 0.1,
                        ready: function() {
                            // Auto-fit the image after initialization
                            this.cropper.zoom(0);
                        }
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
                // Reset zoom after rotation to fit the rotated image
                setTimeout(() => {
                    cropper.zoom(0);
                }, 100);
            }
        });
        
        document.getElementById('rotate-right').addEventListener('click', function() {
            if (cropper) {
                cropper.rotate(90);
                currentRotation += 90;
                // Reset zoom after rotation to fit the rotated image
                setTimeout(() => {
                    cropper.zoom(0);
                }, 100);
            }
        });
        
        // Zoom controls
        document.getElementById('zoom-in').addEventListener('click', function() {
            if (cropper) {
                cropper.zoom(0.1);
            }
        });
        
        document.getElementById('zoom-out').addEventListener('click', function() {
            if (cropper) {
                cropper.zoom(-0.1);
            }
        });
        
        document.getElementById('reset-zoom').addEventListener('click', function() {
            if (cropper) {
                cropper.reset();
                cropper.zoom(0);
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
        
        // Network control functions
        function showNetworkStatus() {
            window.location.href = "{{ url_for('network_status_page') }}";
        }
        
        function toggleNetworkMode() {
            fetch("{{ url_for('api_network_toggle') }}", {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Network mode toggle initiated');
                    setTimeout(() => location.reload(), 2000);
                } else {
                    alert('Failed to toggle network mode: ' + data.message);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Error toggling network mode');
            });
        }
        
        function switchToWiFi() {
            if (confirm('Force switch to WiFi mode?')) {
                fetch("{{ url_for('api_switch_to_wifi') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Switching to WiFi mode...');
                        setTimeout(() => location.reload(), 3000);
                    } else {
                        alert('Failed to switch to WiFi: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error switching to WiFi mode');
                });
            }
        }
        
        function switchToAP() {
            if (confirm('Force switch to Access Point mode?')) {
                fetch("{{ url_for('api_switch_to_ap') }}", {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Switching to AP mode...');
                        setTimeout(() => location.reload(), 3000);
                    } else {
                        alert('Failed to switch to AP: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                    alert('Error switching to AP mode');
                });
            }
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
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)