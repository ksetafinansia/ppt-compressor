#!/usr/bin/env python3
import os
import sys
import argparse
import logging
from PIL import Image
import io

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def compress_image(image_path, scale=0.5, quality=70):
    """
    Compress an image to specified scale and quality, then replace the original image.
    
    Args:
        image_path (str): Path to the image file
        scale (float): Scale factor for dimensions (0.5 = 50% of original size)
        quality (int): Quality level (1-100) for JPG/WebP compression (higher = better quality)
    
    Returns:
        tuple: (success, original_size_kb, compressed_size_kb)
    """
    try:
        # Check if the file exists
        if not os.path.exists(image_path):
            logging.error(f"File does not exist: {image_path}")
            return False, 0, 0
            
        # Get original file size
        original_size = os.path.getsize(image_path) / 1024  # KB
        
        # Open the image
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
            
        # Process the image
        image = Image.open(io.BytesIO(image_bytes))
        
        # Get the original format
        original_format = image.format if image.format else "JPEG"
        
        # Convert to RGB if it's RGBA to avoid issues with JPG
        if image.mode == 'RGBA' and original_format == 'JPEG':
            image = image.convert('RGB')
        
        # Resize the image - make it smaller
        new_width = int(image.width * scale)
        new_height = int(image.height * scale)
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Choose output format based on original
        output_format = original_format
        
        # Create a temporary output file
        temp_output = f"{image_path}.temp"
        
        # Save with compression
        if output_format == "JPEG":
            resized_image.save(temp_output, format=output_format, quality=quality, optimize=True)
        elif output_format == "PNG":
            resized_image.save(temp_output, format=output_format, optimize=True, compress_level=9)
        else:
            # For other formats like GIF or BMP
            resized_image.save(temp_output, format=output_format)
        
        # Get compressed file size
        compressed_size = os.path.getsize(temp_output) / 1024  # KB
        
        # Replace the original file with the compressed one
        os.replace(temp_output, image_path)
        
        # Calculate reduction percentage
        reduction = (1 - (compressed_size / original_size)) * 100 if original_size > 0 else 0
        
        logging.info(f"Successfully compressed: {image_path}")
        logging.info(f"Original size: {original_size:.2f} KB")
        logging.info(f"Compressed size: {compressed_size:.2f} KB")
        logging.info(f"Reduction: {reduction:.1f}%")
        logging.info(f"Resolution: {image.width}x{image.height} → {new_width}x{new_height}")
        
        return True, original_size, compressed_size
    
    except Exception as e:
        logging.error(f"Error compressing {image_path}: {str(e)}")
        # If there was an error, try to clean up the temp file
        if 'temp_output' in locals() and os.path.exists(temp_output):
            os.remove(temp_output)
        return False, 0, 0

def process_directory(directory_path, scale=0.5, quality=70, extensions=None):
    """
    Process all images in a directory.
    
    Args:
        directory_path (str): Path to directory containing images
        scale (float): Scale factor for dimensions
        quality (int): Quality level for compression
        extensions (list): List of file extensions to process
    """
    if extensions is None:
        extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    
    total_files = 0
    processed_files = 0
    total_original_size = 0
    total_compressed_size = 0
    
    for root, _, files in os.walk(directory_path):
        for file in files:
            if any(file.lower().endswith(ext) for ext in extensions):
                file_path = os.path.join(root, file)
                total_files += 1
                
                success, orig_size, comp_size = compress_image(file_path, scale, quality)
                
                if success:
                    processed_files += 1
                    total_original_size += orig_size
                    total_compressed_size += comp_size
    
    if total_files > 0:
        overall_reduction = (1 - (total_compressed_size / total_original_size)) * 100 if total_original_size > 0 else 0
        logging.info(f"Processed {processed_files}/{total_files} images")
        logging.info(f"Total size before: {total_original_size/1024:.2f} MB")
        logging.info(f"Total size after: {total_compressed_size/1024:.2f} MB")
        logging.info(f"Overall reduction: {overall_reduction:.1f}%")
    else:
        logging.info("No image files found to process")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Compress and resize images')
    parser.add_argument('path', help='Path to image file or directory containing images')
    parser.add_argument('--scale', type=float, default=0.5, help='Scale factor for dimensions (0.5 = 50% of original size)')
    parser.add_argument('--quality', type=int, default=70, help='Quality level (1-100) for JPEG compression')
    parser.add_argument('--extensions', nargs='+', default=['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'], 
                        help='File extensions to process when directory is provided')
    
    args = parser.parse_args()
    
    if os.path.isfile(args.path):
        compress_image(args.path, args.scale, args.quality)
    elif os.path.isdir(args.path):
        process_directory(args.path, args.scale, args.quality, args.extensions)
    else:
        logging.error(f"Path does not exist: {args.path}")
        sys.exit(1)