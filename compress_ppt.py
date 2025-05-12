#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
import zipfile
import logging
import argparse
import subprocess
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='ppt_compression.log',
    filemode='w'
)

# Add console handler to display logs in the terminal too
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

def is_ffmpeg_available():
    """
    Check if FFmpeg is available on the system
    
    Returns:
        bool: True if FFmpeg is available, False otherwise
    """
    try:
        # Try both which (Linux/Mac) and where (Windows)
        import platform
        if platform.system() == "Windows":
            result = subprocess.run(["where", "ffmpeg"], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def compress_video(video_path, output_path=None, crf=28, preset="medium"):
    """
    Compress a video file using FFmpeg
    
    Args:
        video_path (str): Path to the video file
        output_path (str, optional): Path to save the compressed video. If None, uses a temp file.
        crf (int): Constant Rate Factor - controls quality (18-28 is good, higher = smaller file)
        preset (str): FFmpeg preset (ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow)
    
    Returns:
        tuple: (success, original_size_kb, compressed_size_kb, output_path)
    """
    if not is_ffmpeg_available():
        logging.error("FFmpeg is not installed. Cannot compress video.")
        return False, 0, 0, None
        
    try:
        # Check if the file exists
        if not os.path.exists(video_path):
            logging.error(f"Video file does not exist: {video_path}")
            return False, 0, 0, None
            
        # Get original file size
        original_size = os.path.getsize(video_path) / 1024  # KB
        
        # Create output path if not provided
        if output_path is None:
            temp_file = f"{video_path}.temp.mp4"
            output_path = temp_file
        
        # Build FFmpeg command for compression
        # -y: Overwrite output files without asking
        # -i: Input file
        # -c:v libx264: Use H.264 codec for video
        # -crf: Constant Rate Factor (quality)
        # -preset: Encoding speed (slower = better compression)
        # -c:a aac: Use AAC codec for audio
        # -b:a 128k: Set audio bitrate to 128kbps
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]
        
        # Run FFmpeg
        logging.info(f"Compressing video: {video_path}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.error(f"FFmpeg error: {result.stderr}")
            return False, 0, 0, None
            
        # Get compressed file size
        compressed_size = os.path.getsize(output_path) / 1024  # KB
        
        # Calculate reduction percentage
        reduction = (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0
        
        logging.info(f"Successfully compressed: {video_path}")
        logging.info(f"Original size: {original_size:.2f} KB")
        logging.info(f"Compressed size: {compressed_size:.2f} KB")
        logging.info(f"Reduction: {reduction:.1f}%")
        
        return True, original_size, compressed_size, output_path
        
    except Exception as e:
        logging.error(f"Error compressing {video_path}: {str(e)}")
        # Clean up if there was an error
        if 'temp_file' in locals() and os.path.exists(temp_file):
            os.remove(temp_file)
        return False, 0, 0, None

def process_video_directory(directory_path, crf=28, preset="medium", extensions=None):
    """
    Process all videos in a directory
    
    Args:
        directory_path (str): Path to directory containing videos
        crf (int): Constant Rate Factor for FFmpeg (quality)
        preset (str): FFmpeg preset for encoding speed
        extensions (list): List of video file extensions to process
    
    Returns:
        tuple: (processed_count, total_original_size, total_compressed_size)
    """
    if not is_ffmpeg_available():
        logging.error("FFmpeg is not installed. Cannot compress videos.")
        logging.error("Please install FFmpeg to enable video compression.")
        return 0, 0, 0
        
    if extensions is None:
        extensions = ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']
        
    total_files = 0
    processed_files = 0
    total_original_size = 0
    total_compressed_size = 0
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                file_path = os.path.join(root, file)
                temp_output = f"{file_path}.temp.mp4"
                
                total_files += 1
                success, orig_size, comp_size, output_path = compress_video(file_path, temp_output, crf, preset)
                
                if success:
                    # Replace original with compressed
                    os.replace(output_path, file_path)
                    processed_files += 1
                    total_original_size += orig_size
                    total_compressed_size += comp_size
    
    if total_files > 0:
        overall_reduction = (1 - (total_compressed_size / total_original_size)) * 100 if total_original_size > 0 else 0
        logging.info(f"Processed {processed_files}/{total_files} videos")
        logging.info(f"Total video size before: {total_original_size/1024:.2f} MB")
        logging.info(f"Total video size after: {total_compressed_size/1024:.2f} MB")
        logging.info(f"Overall video reduction: {overall_reduction:.1f}%")
        
    return processed_files, total_original_size, total_compressed_size

def compress_ppt(ppt_file, image_scale=0.5, image_quality=70, video_crf=28, video_preset="medium"):
    """
    Compress images and videos in PowerPoint file by extracting, compressing and repacking
    
    Args:
        ppt_file (str): Path to the .pptx file
        image_scale (float): Scale factor for image dimensions (0.5 = 50% of original)
        image_quality (int): Quality level for image compression (1-100)
        video_crf (int): Constant Rate Factor for video compression (18-28 recommended)
        video_preset (str): FFmpeg preset for video encoding speed
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Step 1: Make a backup of the file
        ppt_path = Path(ppt_file)
        if not ppt_path.exists() or not ppt_path.is_file():
            logging.error(f"File not found: {ppt_file}")
            return False
        
        # Create backup directory if it doesn't exist
        backup_dir = Path("backup")
        if not backup_dir.exists():
            logging.info(f"Creating backup directory: {backup_dir}")
            backup_dir.mkdir()
            
        backup_filename = f"{ppt_path.stem}{ppt_path.suffix}.backup"
        backup_path = backup_dir / backup_filename
        
        if not backup_path.exists():
            logging.info(f"Creating backup: {backup_path}")
            shutil.copy2(ppt_file, backup_path)
        else:
            logging.info(f"Backup already exists: {backup_path}")
            
        # Create a temporary working directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            extract_path = temp_dir_path / "extracted"
            extract_path.mkdir()
            
            # Step 2: Rename .pptx to .zip (conceptually)
            logging.info(f"Extracting {ppt_file} to temporary directory")
            
            # Step 3: Extract the zip contents
            with zipfile.ZipFile(ppt_file, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
                
            # Step 4: Check if ppt/media directory exists
            media_path = extract_path / "ppt" / "media"
            if media_path.exists() and media_path.is_dir():
                # Step 5a: Compress images using compress_image.py
                logging.info(f"Compressing images in ppt/media directory")
                try:
                    from compress_image import process_directory
                    process_directory(str(media_path), image_scale, image_quality)
                except ImportError:
                    logging.error("Could not import compress_image.py for image compression")
                    
                # Step 5b: Compress videos in ppt/media directory
                logging.info(f"Compressing videos in ppt/media directory")
                process_video_directory(str(media_path), video_crf, video_preset)
            else:
                logging.warning(f"No media directory found at {media_path}")
                
            # Step 6-7: Create a new zip file with the compressed contents
            logging.info(f"Repacking compressed content to {ppt_file}")
            
            # Remove the original file before creating the new one
            if os.path.exists(ppt_file):
                os.remove(ppt_file)
                
            # Zip everything back up
            with zipfile.ZipFile(ppt_file, 'w', compression=zipfile.ZIP_DEFLATED) as new_zip:
                # Walk through all files in the extracted directory and add them to the zip
                for folder_path, _, filenames in os.walk(extract_path):
                    for filename in filenames:
                        file_path = os.path.join(folder_path, filename)
                        # Calculate the path relative to the extract directory
                        arc_name = os.path.relpath(file_path, extract_path)
                        new_zip.write(file_path, arc_name)
                        
            # Step 8: Already has the correct .pptx extension
            logging.info(f"PowerPoint compression completed successfully!")
            
            # Calculate file size reduction
            original_size = os.path.getsize(backup_path) / (1024 * 1024)  # MB
            compressed_size = os.path.getsize(ppt_file) / (1024 * 1024)  # MB
            reduction = (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0
            
            logging.info(f"Original size: {original_size:.2f} MB")
            logging.info(f"Compressed size: {compressed_size:.2f} MB")
            logging.info(f"Reduction: {reduction:.1f}%")
            
            # Explicit cleanup of temporary files (although tempfile context manager handles this)
            logging.info(f"Cleaning up temporary files")
            if os.path.exists(str(extract_path)):
                shutil.rmtree(str(extract_path), ignore_errors=True)
            
            return True
            
    except Exception as e:
        logging.error(f"Error compressing PowerPoint file: {str(e)}")
        return False
        
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Compress images and videos in PowerPoint presentations')
    parser.add_argument('ppt_file', help='Path to the PowerPoint (.pptx) file')
    parser.add_argument('--image-scale', type=float, default=0.5, help='Scale factor for image dimensions (0.5 = 50% of original)')
    parser.add_argument('--image-quality', type=int, default=70, help='Quality level (1-100) for JPEG compression')
    parser.add_argument('--video-crf', type=int, default=28, help='Constant Rate Factor (18-28) for video compression')
    parser.add_argument('--video-preset', choices=['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 
                                                 'medium', 'slow', 'slower', 'veryslow'], 
                       default='medium', help='FFmpeg preset (speed vs compression efficiency)')
    
    args = parser.parse_args()
    
    compress_ppt(args.ppt_file, args.image_scale, args.image_quality, args.video_crf, args.video_preset)