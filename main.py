import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tqdm import tqdm
import keyboard
import time
import sys

# Define exponential backoff parameter
backoff_parameter = 4


# Main function to execute the script
def main():
    # Get the base URL and max_depth from command line arguments
    if len(sys.argv) < 3:
        print("Usage: python script.py <base_url> <max_depth>")
        sys.exit(1)

    base_url = sys.argv[1]
    max_depth = int(sys.argv[2])

    # Set download directory based on the URL structure, starting from "downloaded_files" followed by the URL path
    url_path = urlparse(base_url).path.lstrip("/")
    download_directory = os.path.join("downloaded_files", url_path)

    # Create the directory if it doesn't exist
    if not os.path.exists(download_directory):
        os.makedirs(download_directory)
        print(f"Created download directory: {download_directory}")

    # Start the recursive download process with retry and max depth control
    print(
        f"Starting recursive download from base URL: {base_url}, max depth: {max_depth}"
    )
    traverse_and_download(base_url, download_directory, max_depth, current_depth=0)


# Function to clean and validate filenames
def clean_filename(url):
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    print(f"Cleaned filename: {filename}")
    return filename


# Function to clean directory names to avoid security issues
def clean_directory_name(name):
    # Remove any dangerous characters like ".." and "/"
    cleaned_name = name.replace("..", "").replace("/", "").replace("\\", "")
    print(f"Cleaned directory name: {cleaned_name}")
    return cleaned_name


# Function to download and save a file with support for resuming, speed limiting, monitoring speed, and pause/resume
def download_file(file_url, folder, speed_limit=None, retries=5):
    """
    Downloads a file with optional speed limit (in bytes per second) and pause/resume support.
    Press 'p' to pause and 'r' to resume.
    """
    file_name = clean_filename(file_url)

    # Skip invalid file names or empty names
    if not file_name or file_name in [".", ".."]:
        print(f"Skipping invalid filename: {file_name}")
        return

    file_path = os.path.join(folder, file_name)
    print(f"File path set to: {file_path}")

    attempt = 0
    success = False

    while attempt < retries and not success:
        try:
            print(f"Attempting to download file: {file_name}, Attempt: {attempt + 1}")
            # Send a HEAD request to get the total file size on the server
            response = requests.head(file_url)

            if response.status_code != 200:
                print(f"Failed to retrieve file information: {file_url}")
                raise requests.exceptions.RequestException(
                    f"HTTP Error: {response.status_code}"
                )

            # Get the size of the file from the server
            server_file_size = int(response.headers.get("content-length", 0))
            print(f"Server file size: {server_file_size} bytes")

            # Check if the file already exists locally
            if os.path.exists(file_path):
                local_file_size = os.path.getsize(file_path)
                print(f"Local file size: {local_file_size} bytes")

                if local_file_size == server_file_size:
                    print(
                        f"File already fully downloaded: {file_name}, skipping download."
                    )
                    return
                elif local_file_size < server_file_size:
                    print(f"Resuming download for: {file_name}")
                    resume_header = {"Range": f"bytes={local_file_size}-"}
                else:
                    print(
                        f"Local file is larger than the server file: {file_name}, re-downloading..."
                    )
                    local_file_size = 0
                    resume_header = None
            else:
                local_file_size = 0
                resume_header = None

            # Download the remaining part of the file
            response = requests.get(file_url, headers=resume_header, stream=True)

            if response.status_code in (
                200,
                206,
            ):  # 206 is for partial content (resumed download)
                total_size = (
                    int(response.headers.get("content-length", 0)) + local_file_size
                )
                print(f"Total size to download: {total_size} bytes")

                mode = "ab" if resume_header else "wb"

                with open(file_path, mode) as file, tqdm(
                    desc=file_name,
                    total=total_size,
                    initial=local_file_size,  # Start the progress bar at the local file size
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    leave=True,
                ) as progress_bar:
                    for data in response.iter_content(chunk_size=8192):
                        if not data:
                            continue  # Skip if there's no data

                        file.write(data)
                        progress_bar.update(len(data))

                        # Speed limiting
                        if speed_limit:
                            time.sleep(
                                1024 / speed_limit
                            )  # Sleep to maintain the speed limit in bytes per second

                        # Pause/Resume functionality
                        if pause_check():
                            print(f"\nPaused download for: {file_name}")
                            # Wait for user to press 'r' to resume
                            while not resume_check():
                                time.sleep(1)
                            print(f"\nResuming download for: {file_name}")

                print(f"Downloaded: {file_name}")
                success = True  # Mark as successful if no exception occurred

            else:
                raise requests.exceptions.RequestException(
                    f"Failed to download: {file_name}, Status code: {response.status_code}"
                )

        except (
            requests.exceptions.RequestException,
            requests.exceptions.ConnectionError,
        ) as e:
            attempt += 1
            backoff_time = backoff_parameter**attempt
            print(f"Attempt {attempt} failed for {file_name}: {e}")
            print(f"Retrying after {backoff_time} seconds...")
            time.sleep(backoff_time)

    if not success:
        print(f"Failed to download {file_name} after {retries} attempts.")


# Function to check if the user wants to pause the download
def pause_check():
    if keyboard.is_pressed("p"):
        return True
    return False


def resume_check():
    if keyboard.is_pressed("r"):
        return True
    return False


# Function to recursively traverse directories and download files, with max depth control
def traverse_and_download(url, folder, max_depth, current_depth, retries=100):
    if current_depth > max_depth:
        print(f"Max depth reached: {current_depth}, stopping recursion.")
        return

    attempt = 1
    success = False
    sleep_time = max(10, backoff_parameter**attempt)
    while attempt < retries and not success:
        try:
            print(f"Accessing URL: {url}, Attempt: {attempt}, Depth: {current_depth}")
            response = requests.get(url)
            if response.status_code == 200:
                success = True
                print(f"Successfully accessed URL: {url}")
                soup = BeautifulSoup(response.text, "html.parser")

                links = soup.find_all("a")
                print(f"Found {len(links)} links on the page.")

                for link in links:
                    href = link.get("href")

                    # Skip invalid links, directory navigation, and query parameters
                    if not href or href in ["Go up", "..", "/"] or "?" in href:
                        print(f"Skipping invalid link: {href}")
                        continue

                    full_url = urljoin(url, href)
                    print(f"Processing link: {full_url}")

                    if href.endswith("/"):
                        # Clean directory name to avoid issues with ".." or illegal characters
                        clean_dir_name = clean_directory_name(href.strip("/"))
                        new_folder = os.path.join(folder, clean_dir_name)

                        # Ensure the directory name is valid
                        if not clean_dir_name:
                            print(f"Invalid directory name after cleaning: {href}")
                            continue

                        if not os.path.exists(new_folder):
                            os.makedirs(new_folder)
                            print(f"Created new folder: {new_folder}")
                        traverse_and_download(
                            full_url, new_folder, max_depth, current_depth + 1
                        )
                    else:
                        # Ask the user whether they want to download the file or skip
                        user_input = (
                            input(
                                f"Do you want to download the file {full_url}? (yes/no): "
                            )
                            .strip()
                            .lower()
                        )

                        if user_input == "yes":
                            try:
                                print(f"Starting download for file: {full_url}")
                                download_file(
                                    full_url, folder, speed_limit=1024 * 100000
                                )
                            except Exception as e:
                                print(
                                    f"Failed to download file: {full_url}. Error: {e}"
                                )
                        else:
                            print(f"Skipping file: {full_url}")

            else:
                print(
                    f"Failed to access the webpage. Status code: {response.status_code}"
                )
                # Throw an exception to trigger the retry mechanism
                raise requests.exceptions.RequestException(
                    f"Failed to access the webpage. Status code: {response.status_code}"
                )
        except Exception as e:
            print(f"Request failed: {e}")
            print(f"Server unavailable, retrying after {sleep_time} seconds.")
            time.sleep(sleep_time)  # Exponential backoff
        finally:
            attempt += 1

    if not success:
        print(f"Failed to access the webpage after {retries} attempts.")


if __name__ == "__main__":
    main()
