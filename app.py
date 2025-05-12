#!/usr/bin/env python3
import os
import logging
import tempfile
import uuid
import time
import json
import threading
from pathlib import Path
from flask import Flask, request, render_template, send_file, redirect, url_for, flash, session, jsonify
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

# Add a memory handler to capture logs for the web interface
class MemoryLogHandler(logging.Handler):
    def __init__(self, capacity=100):
        logging.Handler.__init__(self)
        self.capacity = capacity
        self.logs = []
        self.formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    def emit(self, record):
        self.logs.append(self.formatter.format(record))
        if len(self.logs) > self.capacity:
            self.logs.pop(0)  # Remove oldest log entry if capacity reached

    def get_logs(self):
        return self.logs

# Create and add memory handler
memory_handler = MemoryLogHandler()
memory_handler.setLevel(logging.INFO)
logging.getLogger('').addHandler(memory_handler)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))  # Used for flashing messages

# Configure upload settings - use environment paths for cloud deployment
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Check if running on Replit
is_replit = 'REPL_ID' in os.environ
if is_replit:
    # Use Replit persistent storage
    REPLIT_DATA_DIR = os.path.join(BASE_DIR, '.data')
    os.makedirs(REPLIT_DATA_DIR, exist_ok=True)
    UPLOAD_FOLDER = os.path.join(REPLIT_DATA_DIR, 'uploads')
    DOWNLOAD_FOLDER = os.path.join(REPLIT_DATA_DIR, 'downloads')
    BACKUP_FOLDER = os.path.join(REPLIT_DATA_DIR, 'backup')
    logging.info(f"Using Replit persistent storage at {REPLIT_DATA_DIR}")
else:
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

# Simple in-memory task queue
tasks = {}

class CompressionTask:
    def __init__(self, task_id, file_path, output_path, params):
        self.task_id = task_id
        self.file_path = file_path
        self.output_path = output_path
        self.params = params
        self.status = "pending"
        self.progress = 0
        self.message = "Preparing to compress..."
        self.error = None
        self.result = None
        self.compressed_filename = None
        self.original_filename = None

def compress_file_task(task):
    """Background task to compress a PowerPoint file with progress tracking"""
    try:
        task.status = "processing"
        task.message = "Extracting PowerPoint content..."
        task.progress = 0.1
        
        # We need to modify compress_ppt to accept a progress callback
        # For now, we'll simulate progress updates
        time.sleep(1)  # Simulate some processing time
        
        task.progress = 0.3
        task.message = "Compressing images..."
        time.sleep(1)
        
        # Run the compression (the actual function doesn't report progress yet)
        success = compress_ppt(
            ppt_file=task.file_path,
            output_path=task.output_path, 
            image_scale=task.params['image_scale'],
            image_quality=task.params['image_quality'],
            video_crf=task.params['video_crf'],
            video_preset=task.params['video_preset']
        )
        
        if success:
            task.progress = 1.0
            task.status = "complete"
            task.message = "Compression completed successfully!"
            task.compressed_filename = os.path.basename(task.output_path)
            task.original_filename = task.params['original_filename']
            # Store the result without using url_for outside of app context
            task.result = {
                "success": True,
                "compressed_filename": task.compressed_filename,
                "original_filename": task.original_filename,
                # Use a simple string instead of url_for
                "redirect_url": "/download"
            }
        else:
            task.status = "error"
            task.error = "Failed to compress the PowerPoint file"
    except Exception as e:
        task.status = "error"
        task.error = str(e)
        logging.error(f"Error in compression task: {e}")

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

@app.route('/', methods=['GET'])
def index():
    """Main page with upload form"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Ajax endpoint to handle file upload with progress tracking"""
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"})
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"})
    
    if file and allowed_file(file.filename):
        # Check file size before saving
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer to beginning
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                "status": "error", 
                "message": f"File is too large: {format_size(file_size)}. Maximum allowed size is {format_size(MAX_FILE_SIZE)}."
            })
            
        # Generate a unique filename to prevent conflicts
        unique_id = uuid.uuid4().hex[:8]
        task_id = uuid.uuid4().hex
        original_filename = secure_filename(file.filename)
        filename = f"{unique_id}_{original_filename}"
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(upload_path)
        
        # Get compression parameters from the form
        image_scale = float(request.form.get('image_scale', 0.5))
        image_quality = int(request.form.get('image_quality', 70))
        video_crf = int(request.form.get('video_crf', 28))
        video_preset = request.form.get('video_preset', 'medium')
        
        # Store information in the session
        session['uploaded_filename'] = filename
        session['original_filename'] = original_filename
        
        # Prepare output path
        output_filename = f"compressed_{filename}"
        output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)
        
        # Copy the uploaded file to the output path
        import shutil
        shutil.copy2(upload_path, output_path)
        
        # Create a task
        task = CompressionTask(
            task_id=task_id,
            file_path=upload_path,
            output_path=output_path,
            params={
                'image_scale': image_scale,
                'image_quality': image_quality,
                'video_crf': video_crf,
                'video_preset': video_preset,
                'original_filename': original_filename
            }
        )
        
        # Store the task in our in-memory queue
        tasks[task_id] = task
        
        # Start the compression in a background thread
        thread = threading.Thread(target=compress_file_task, args=(task,))
        thread.daemon = True
        thread.start()
        
        # Store task details in session for the download page
        session['task_id'] = task_id
        session['compressed_filename'] = output_filename
        
        # Return task ID for client to poll status
        return jsonify({
            "status": "processing", 
            "task_id": task_id,
            "message": "File uploaded, starting compression..."
        })
        
    else:
        allowed_ext_list = ", ".join([f".{ext}" for ext in ALLOWED_EXTENSIONS_SET])
        return jsonify({
            "status": "error",
            "message": f"Invalid file type. Allowed file types are: {allowed_ext_list}"
        })

@app.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Check the status of a background task"""
    if task_id not in tasks:
        return jsonify({"status": "error", "message": "Task not found"})
    
    task = tasks[task_id]
    
    if task.status == "complete":
        # Clear task from memory after completion (optional)
        if task.result:
            response = {"status": "complete", "redirect_url": task.result["redirect_url"]}
            # tasks.pop(task_id, None)  # Uncomment to remove completed tasks
            return jsonify(response)
        else:
            return jsonify({
                "status": "error",
                "message": "Task completed but no result found"
            })
    elif task.status == "error":
        return jsonify({
            "status": "error",
            "error": task.error
        })
    else:
        return jsonify({
            "status": "processing",
            "progress": task.progress,
            "message": task.message
        })

@app.route('/download')
def download_file():
    """Download page for the compressed file"""
    # Check both session and task_id parameter for file information
    task_id = request.args.get('task_id') or session.get('task_id')
    
    # First try to get the file from the task if available
    if task_id and task_id in tasks:
        task = tasks[task_id]
        if task.status == "complete" and task.compressed_filename:
            compressed_filename = task.compressed_filename
            original_filename = task.original_filename or 'presentation.pptx'
            download_path = os.path.join(DOWNLOAD_FOLDER, compressed_filename)
            
            if os.path.exists(download_path):
                # Store in session for future access
                session['compressed_filename'] = compressed_filename
                session['original_filename'] = original_filename
                return render_template('download.html', filename=compressed_filename, original_filename=original_filename)
    
    # Fall back to session data if task not found or incomplete
    if 'compressed_filename' not in session:
        flash('No compressed file available')
        return redirect(url_for('index'))
    
    compressed_filename = session['compressed_filename']
    original_filename = session.get('original_filename', 'presentation.pptx')
    download_path = os.path.join(DOWNLOAD_FOLDER, compressed_filename)
    
    if not os.path.exists(download_path):
        flash('Compressed file not found')
        return redirect(url_for('index'))
    
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

@app.route('/logs')
def get_logs():
    """Return the captured logs from the memory handler"""
    logs = memory_handler.get_logs()
    return jsonify({"logs": logs})

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
    
    # Clean up old tasks
    old_tasks = []
    for task_id, task in list(tasks.items()):
        if hasattr(task, 'created_at') and time.time() - task.created_at > 3600:
            old_tasks.append(task_id)
    for task_id in old_tasks:
        tasks.pop(task_id, None)
    
    return f"Cleaned up: {uploads_count} uploads, {downloads_count} downloads, {backups_count} backups, {len(old_tasks)} tasks", 200

if __name__ == '__main__':
    # Get port from environment variable or default to 5000
    port = int(os.environ.get('PORT', 5000))
    
    # Run the Flask application
    app.run(host='0.0.0.0', port=port, debug=False)