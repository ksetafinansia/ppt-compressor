#!/usr/bin/env python3
import os
import logging
import tempfile
import uuid
from pathlib import Path
from flask import Flask, request, render_template, send_file, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from compress_ppt import compress_ppt, ALLOWED_EXTENSIONS, MAX_FILE_SIZE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='webapp.log',
    filemode='w'
)

# Add console handler to display logs in the terminal too
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))  # Used for flashing messages

# Configure upload settings - use environment paths for cloud deployment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Use Render's persistent disk if available, otherwise use local paths
RENDER_DATA_DIR = os.environ.get('RENDER_DISK_MOUNT_PATH', '/var/data')
if os.path.exists(RENDER_DATA_DIR):
    UPLOAD_FOLDER = os.path.join(RENDER_DATA_DIR, 'uploads')
    DOWNLOAD_FOLDER = os.path.join(RENDER_DATA_DIR, 'downloads')
    BACKUP_FOLDER = os.path.join(RENDER_DATA_DIR, 'backup')
    logging.info(f"Using Render persistent storage at {RENDER_DATA_DIR}")
else:
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'uploads'))
    DOWNLOAD_FOLDER = os.environ.get('DOWNLOAD_FOLDER', os.path.join(BASE_DIR, 'downloads'))
    BACKUP_FOLDER = os.environ.get('BACKUP_FOLDER', os.path.join(BASE_DIR, 'backup'))
    logging.info("Using local storage directories")

ALLOWED_EXTENSIONS_SET = {ext.strip('.') for ext in ALLOWED_EXTENSIONS}  # Strip the dot from extensions

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# Configure app settings
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE  # Use the same 1.5GB limit from compress_ppt.py

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS_SET

def format_size(size_bytes):
    """Format file size in bytes to a human-readable string"""
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        # If user does not select file, browser also submits an empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            # Check file size before saving
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)  # Reset file pointer to beginning
            
            if file_size > MAX_FILE_SIZE:
                flash(f'File is too large: {format_size(file_size)}. Maximum allowed size is {format_size(MAX_FILE_SIZE)}.')
                return redirect(request.url)
                
            # Generate a unique filename to prevent conflicts
            unique_id = uuid.uuid4().hex[:8]
            original_filename = secure_filename(file.filename)
            filename = f"{unique_id}_{original_filename}"
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(upload_path)
            
            # Get compression parameters from the form
            image_scale = float(request.form.get('image_scale', 0.5))
            image_quality = int(request.form.get('image_quality', 70))
            video_crf = int(request.form.get('video_crf', 28))
            video_preset = request.form.get('video_preset', 'medium')
            
            # Store the filename in the session
            session['uploaded_filename'] = filename
            session['original_filename'] = original_filename
            
            # Compress the PPT file
            output_path = os.path.join(DOWNLOAD_FOLDER, f"compressed_{filename}")
            
            # Copy the uploaded file to the output path
            import shutil
            shutil.copy2(upload_path, output_path)
            
            # Compress the file in the output path
            success = compress_ppt(
                output_path, 
                image_scale=image_scale,
                image_quality=image_quality,
                video_crf=video_crf,
                video_preset=video_preset
            )
            
            if success:
                # Store compressed filename in session for download
                session['compressed_filename'] = f"compressed_{filename}"
                return redirect(url_for('download_file'))
            else:
                flash('Error compressing file')
                return redirect(request.url)
        
        else:
            allowed_ext_list = ", ".join([f".{ext}" for ext in ALLOWED_EXTENSIONS_SET])
            flash(f'Invalid file type. Allowed file types are: {allowed_ext_list}')
            return redirect(request.url)
    
    return render_template('index.html')

@app.route('/download')
def download_file():
    if 'compressed_filename' not in session:
        flash('No compressed file available')
        return redirect(url_for('upload_file'))
    
    compressed_filename = session['compressed_filename']
    original_filename = session.get('original_filename', 'presentation.pptx')
    download_path = os.path.join(DOWNLOAD_FOLDER, compressed_filename)
    
    if not os.path.exists(download_path):
        flash('Compressed file not found')
        return redirect(url_for('upload_file'))
    
    return render_template('download.html', filename=compressed_filename, original_filename=original_filename)

@app.route('/get_file/<filename>')
def get_file(filename):
    """Serve the file for download"""
    original_filename = session.get('original_filename', 'compressed_presentation.pptx')
    download_name = f"compressed_{original_filename}"
    
    return send_file(
        os.path.join(DOWNLOAD_FOLDER, filename),
        as_attachment=True,
        download_name=download_name
    )

# Periodic cleanup to avoid filling disk space
@app.route('/cleanup', methods=['GET'])
def cleanup():
    """Admin route to clean up old files"""
    import time
    import shutil
    
    # Only allow authorized access
    auth_key = request.args.get('key')
    if not auth_key or auth_key != os.environ.get('CLEANUP_KEY', 'clean-my-files'):
        return "Unauthorized", 401
    
    # Clean files older than 1 hour (3600 seconds)
    threshold = time.time() - 3600
    
    # Cleanup function for a directory
    def cleanup_dir(dir_path):
        count = 0
        if not os.path.exists(dir_path):
            return 0
            
        for filename in os.listdir(dir_path):
            file_path = os.path.join(dir_path, filename)
            try:
                if os.path.isfile(file_path) and os.path.getmtime(file_path) < threshold:
                    os.unlink(file_path)
                    count += 1
            except Exception as e:
                logging.error(f"Error deleting {file_path}: {e}")
        return count
    
    # Clean up uploads, downloads and backup folders
    uploads_count = cleanup_dir(UPLOAD_FOLDER)
    downloads_count = cleanup_dir(DOWNLOAD_FOLDER)
    backups_count = cleanup_dir(BACKUP_FOLDER)
    
    return f"Cleaned up: {uploads_count} uploads, {downloads_count} downloads, {backups_count} backups", 200

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Run the Flask application
    app.run(host='0.0.0.0', port=port, debug=False)