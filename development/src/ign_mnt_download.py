import os
import time
import urllib.request
import urllib.error
import urllib.parse
import sys
import ssl
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Configuration
BASE_URL = "https://data.geopf.fr/wms-r"
RETRIES = 2
RETRY_DELAY = 2  # seconds
MAX_WORKERS = 8

# Create an unverified SSL context
ssl_context = ssl._create_unverified_context()

# Global flag for graceful shutdown
shutdown_event = None

def parse_filename(filename):
    """
    Parses the filename to extract X and Y coordinates.
    Expected format: LHD_FXX_XXXX_YYYY
    """
    parts = filename.strip().split('_')
    if len(parts) < 4:
        raise ValueError(f"Invalid filename format: {filename}")

    try:
        x_km = int(parts[2])
        y_km = int(parts[3])
    except ValueError:
        raise ValueError(f"Could not parse coordinates from: {filename}")

    return x_km, y_km

def calculate_bbox(x_km, y_km):
    """
    Calculates the BBOX based on 1km tiles with 0.5m resolution logic.
    Ref:
    MinX = X * 1000 - 0.25
    MaxX = (X + 1) * 1000 - 0.25
    MinY = (Y - 1) * 1000 + 0.25
    MaxY = Y * 1000 + 0.25
    """
    min_x = x_km * 1000 - 0.25
    max_x = (x_km + 1) * 1000 - 0.25
    min_y = (y_km - 1) * 1000 + 0.25
    max_y = y_km * 1000 + 0.25

    return f"{min_x},{min_y},{max_x},{max_y}"

def download_file(url, filepath, debug_str):
    """
    Downloads the file from the URL to the filepath with retries.
    Cleans up partial files on failure or interrupt.
    """
    for attempt in range(RETRIES + 1):
        try:
            print(f"Downloading {os.path.basename(filepath)} {debug_str} (Attempt {attempt + 1}/{RETRIES + 1})...")

            with urllib.request.urlopen(url, context=ssl_context) as response, open(filepath, 'wb') as out_file:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    out_file.write(chunk)

            # Check if file is valid (non-zero size)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"Successfully downloaded: {filepath}")
                return True
            else:
                print(f"Downloaded file is empty: {filepath}")
                if os.path.exists(filepath):
                    os.remove(filepath)

        except urllib.error.URLError as e:
            print(f"Error downloading {filepath}: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
        except KeyboardInterrupt:
            if os.path.exists(filepath):
                os.remove(filepath)
            raise
        except Exception as e:
            print(f"Unexpected error downloading {filepath}: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)

        if attempt < RETRIES:
            print(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)

    return False

def process_tile(tile_info):
    """
    Process a single tile download. Returns (success, message).
    tile_info is a dict with: tile_name, bbox, output_path, idx, total_tiles
    """
    tile_name = tile_info['tile_name']
    bbox = tile_info['bbox']
    output_path = tile_info['output_path']
    idx = tile_info['idx']
    total_tiles = tile_info['total_tiles']

    # Check if file exists and is non-zero
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return True, f"({idx}/{total_tiles}) File already exists and is valid: {output_path}"

    # Construct URL
    output_filename = os.path.basename(output_path)
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "EXCEPTIONS": "text/xml",
        "REQUEST": "GetMap",
        "LAYERS": "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93",
        "FORMAT": "image/geotiff",
        "STYLES": "",
        "CRS": "EPSG:2154",
        "BBOX": bbox,
        "WIDTH": "2000",
        "HEIGHT": "2000",
        "FILENAME": output_filename
    }

    url = BASE_URL + "?" + urllib.parse.urlencode(params)

    success = download_file(url, output_path, debug_str=bbox)
    if not success:
        return False, f"({idx}/{total_tiles}) Failed to download {tile_name} after retries."
    return True, f"({idx}/{total_tiles}) Successfully downloaded {tile_name}"

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\nReceived interrupt signal. Waiting for ongoing downloads to complete or cleaning up...")
    raise KeyboardInterrupt()

def main(input_files, output_dir):
    global shutdown_event

    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Ensure download directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Collect tiles by input file
    tiles_by_file = {}
    for input_file in input_files:
        input_path = input_file
        if not os.path.exists(input_path):
            input_path = os.path.join(os.getcwd(), input_file)
        if not os.path.exists(input_path):
            print(f"Error: Input file not found at {input_path}")
            sys.exit(1)

        # Use input filename (without path/extension) as subfolder name
        file_basename = Path(input_path).stem
        file_output_dir = os.path.join(output_dir, file_basename)
        if not os.path.exists(file_output_dir):
            os.makedirs(file_output_dir)

        print(f"Reading from {input_path}")
        with open(input_path, 'r') as f:
            lines = f.readlines()

        tiles = [line.strip() for line in lines if line.strip()]
        tiles_by_file[file_basename] = (file_output_dir, tiles)

    # Flatten all tiles with their metadata for parallel processing
    all_tasks = []
    total_tiles = 0
    for file_basename, (file_output_dir, tiles) in tiles_by_file.items():
        total_tiles += len(tiles)

    idx = 0
    for file_basename, (file_output_dir, tiles) in tiles_by_file.items():
        for tile_name in tiles:
            idx += 1
            try:
                x_km, y_km = parse_filename(tile_name)
                bbox = calculate_bbox(x_km, y_km)
                output_filename = f"{tile_name}_MNT_O_0M50_LAMB93_IGN69.tif"
                output_path = os.path.join(file_output_dir, output_filename)

                all_tasks.append({
                    'tile_name': tile_name,
                    'bbox': bbox,
                    'output_path': output_path,
                    'idx': idx,
                    'total_tiles': total_tiles
                })
            except ValueError as e:
                print(f"({idx}/{total_tiles}) Skipping invalid tile '{tile_name}': {e}")

    print(f"Found {total_tiles} unique tiles to process.")

    # Process tiles in parallel
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_tile, task): task for task in all_tasks}
            for future in as_completed(futures):
                success, message = future.result()
                print(message)
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ign-mnt-download.py <input_file> [input_file2 ...] [output_dir]")
        sys.exit(1)

    # Last argument is output_dir if it doesn't exist as a file
    args = sys.argv[1:]
    output_dir = "download"
    input_files = args

    # Check if last argument is a directory or doesn't exist as a file (treat as output_dir)
    if len(args) > 1 and not os.path.isfile(args[-1]):
        output_dir = args[-1]
        input_files = args[:-1]

    main(input_files, output_dir)
