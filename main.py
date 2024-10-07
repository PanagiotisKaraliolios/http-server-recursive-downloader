import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from tqdm import tqdm

# URL of the webpage containing the files
base_url = "https://csar.birds.web.id/v1/CSA_08hx000300h/official-table/table3/"

# Directory where files will be saved
download_directory = "downloaded_files"

# Create the directory if it doesn't exist
if not os.path.exists(download_directory):
    os.makedirs(download_directory)


# Function to clean and validate filenames
def clean_filename(url):
    parsed_url = urlparse(url)
    filename = os.path.basename(parsed_url.path)
    return filename


# Function to clean directory names to avoid security issues
def clean_directory_name(name):
    # Remove any dangerous characters like ".." and "/"
    cleaned_name = name.replace("..", "").replace("/", "").replace("\\", "")
    return cleaned_name


# Function to download and save a file with a progress bar
def download_file(file_url, folder):
    file_name = clean_filename(file_url)

    # Skip invalid file names or empty names
    if not file_name or file_name in [".", ".."]:
        return

    file_path = os.path.join(folder, file_name)

    response = requests.get(file_url, stream=True)

    if response.status_code == 200:
        total_size = int(response.headers.get("content-length", 0))

        with open(file_path, "wb") as file, tqdm(
            desc=file_name,
            total=total_size,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            leave=False,
        ) as progress_bar:
            for data in response.iter_content(chunk_size=1024):
                file.write(data)
                progress_bar.update(len(data))
        print(f"Downloaded: {file_name}")
    else:
        print(f"Failed to download: {file_name}")


# Function to recursively traverse directories and download files
def traverse_and_download(url, folder, retries=5):
    attempt = 0
    success = False
    while attempt < retries and not success:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                success = True
                soup = BeautifulSoup(response.text, "html.parser")

                links = soup.find_all("a")

                for link in links:
                    href = link.get("href")

                    # Skip invalid links, directory navigation, and query parameters
                    if not href or href in ["Go up", "..", "/"] or "?" in href:
                        continue

                    full_url = urljoin(url, href)

                    if href.endswith("/"):
                        # Clean directory name to avoid issues with ".." or illegal characters
                        clean_dir_name = clean_directory_name(href.strip("/"))
                        new_folder = os.path.join(folder, clean_dir_name)

                        # Ensure the directory name is valid
                        if not clean_dir_name:
                            continue

                        if not os.path.exists(new_folder):
                            os.makedirs(new_folder)
                        traverse_and_download(full_url, new_folder)
                    else:
                        download_file(full_url, folder)
            else:
                print(
                    f"Failed to access the webpage. Status code: {response.status_code}"
                )
                if response.status_code == 503:
                    print("Server unavailable, retrying...")
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    break
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            time.sleep(2**attempt)  # Exponential backoff
        finally:
            attempt += 1

    if not success:
        print(f"Failed to access the webpage after {retries} attempts.")


# Start the recursive download process with retry
traverse_and_download(base_url, download_directory)
