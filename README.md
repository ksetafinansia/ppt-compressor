# PowerPoint Compressor

A web application to compress PowerPoint presentations by optimizing embedded images and media files, reducing the overall file size while maintaining visual quality.

## Features

- Upload PowerPoint files (.pptx)
- Automatically compress images within presentations
- Download the compressed presentation
- Maintain presentation structure and formatting
- Simple web interface

## Installation

1. Clone this repository
2. Set up a virtual environment (recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the application:
   ```
   python app.py
   ```

## Usage

1. Open the application in a web browser
2. Upload your PowerPoint file
3. Wait for the compression to complete
4. Download your compressed presentation

## Tech Stack

- Python
- Flask (Web Framework)
- python-pptx (PowerPoint manipulation)
- Pillow (Image processing)

## TODO

- [ ] Ensure virtual environment (venv) is properly set up but excluded from version control
- [ ] Add more image compression options
- [ ] Support for additional file formats

## License

[MIT](LICENSE)