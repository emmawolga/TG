import os
import re
import sys
import json
import time
import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


def clean_filename(name):
    """Remove invalid filesystem characters."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def download(url, path):
    """Download a file from url and save to path."""
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code == 200:
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            print("✅ Downloaded:", path)
        else:
            print("❌ Failed (HTTP {}): {}".format(r.status_code, url))
    except Exception as e:
        print("❌ Error downloading {}: {}".format(url, e))


def extract_file_links(driver):
    """
    Extract document and audio file download links from the Telegram embed page.
    Returns a list of (url, suggested_filename) tuples.
    """
    file_items = []
    seen_urls = set()

    # Helper to add a file if not duplicate
    def add_file(url, filename):
        if not url or url in seen_urls:
            return
        seen_urls.add(url)
        if not filename:
            # derive from URL if no filename available
            filename = os.path.basename(url.split('?')[0])
        filename = clean_filename(filename)
        if not filename:
            filename = "file"
        file_items.append((url, filename))

    # 1. Document attachments (most common for files)
    docs = driver.find_elements(By.CSS_SELECTOR, ".tgme_widget_message_document")
    for doc in docs:
        try:
            link_elem = doc.find_element(By.CSS_SELECTOR, ".tgme_widget_message_document_download")
            url = link_elem.get_attribute("href")
            if not url:
                continue
            # get the filename from the title span
            try:
                title_elem = doc.find_element(By.CSS_SELECTOR, ".tgme_widget_message_document_title")
                filename = title_elem.text.strip()
            except:
                filename = ""
            add_file(url, filename)
        except Exception:
            continue

    # 2. Audio attachments (if any)
    audios = driver.find_elements(By.CSS_SELECTOR, ".tgme_widget_message_audio")
    for audio in audios:
        try:
            link_elem = audio.find_element(By.CSS_SELECTOR, ".tgme_widget_message_audio_download")
            url = link_elem.get_attribute("href")
            if not url:
                continue
            try:
                title_elem = audio.find_element(By.CSS_SELECTOR, ".tgme_widget_message_audio_title")
                filename = title_elem.text.strip()
            except:
                filename = ""
            add_file(url, filename)
        except Exception:
            continue

    # 3. Fallback: any link with a download attribute or typical file extensions
    all_links = driver.find_elements(By.TAG_NAME, "a")
    file_extensions = ('.zip', '.rar', '.7z', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                       '.ppt', '.pptx', '.txt', '.mp3', '.ogg', '.wav', '.flac',
                       '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')
    for link in all_links:
        href = link.get_attribute("href")
        if not href:
            continue
        if href in seen_urls:
            continue
        # check for download attribute or extension
        if link.get_attribute("download") is not None:
            add_file(href, "")
        elif any(href.lower().endswith(ext) for ext in file_extensions):
            # avoid capturing images that are part of the layout
            if "logo" in href or "avatar" in href:
                continue
            add_file(href, "")

    return file_items


def main(link):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # enable network logging for video detection
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    embed_url = link + "?embed=1&mode=tme"
    print("🌐 Opening:", embed_url)
    driver.get(embed_url)
    time.sleep(10)  # wait for page to load

    # Create output folder based on the original link
    folder = clean_filename(link.replace("https://", "").replace("/", "_"))
    os.makedirs(folder, exist_ok=True)

    # -------------------------
    # CLICK VIDEO IF EXISTS
    # -------------------------
    try:
        video = driver.find_element(By.TAG_NAME, "video")
        driver.execute_script("arguments[0].play();", video)
        print("▶️ Video playback triggered")
        time.sleep(5)
    except Exception:
        pass

    # -------------------------
    # READ NETWORK LOGS FOR VIDEOS
    # -------------------------
    logs = driver.get_log("performance")
    video_urls = set()
    for entry in logs:
        try:
            message = json.loads(entry["message"])
            message = message["message"]
            if message["method"] != "Network.responseReceived":
                continue
            response = message["params"]["response"]
            url = response.get("url", "")
            mime = response.get("mimeType", "")
            if ".mp4" in url or "video" in mime:
                video_urls.add(url)
        except Exception:
            continue

    # -------------------------
    # EXTRACT FILE DOWNLOAD LINKS
    # -------------------------
    file_items = extract_file_links(driver)

    # -------------------------
    # DOWNLOAD VIDEOS
    # -------------------------
    video_count = 0
    for url in video_urls:
        video_count += 1
        print("🎬 Found video:", url)
        download(url, os.path.join(folder, f"video_{video_count}.mp4"))

    # -------------------------
    # DOWNLOAD FILES
    # -------------------------
    for idx, (url, filename) in enumerate(file_items, start=1):
        print("📄 Found file:", filename or url)
        # if filename already has extension, use as is; else try to infer from URL
        if not filename or '.' not in filename:
            ext = os.path.splitext(url.split('?')[0])[1]
            if ext:
                filename = f"file_{idx}{ext}"
            else:
                filename = f"file_{idx}"
        download(url, os.path.join(folder, filename))

    # -------------------------
    # SAVE CAPTION
    # -------------------------
    try:
        caption = driver.find_element(By.CLASS_NAME, "tgme_widget_message_text").text
        with open(os.path.join(folder, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(caption)
        print("📝 Caption saved")
    except Exception:
        print("⚠️ No caption found")

    driver.quit()

    if not video_urls and not file_items:
        print("❌ No videos or files found")
    else:
        print(f"✅ Finished. Downloaded {len(video_urls)} video(s) and {len(file_items)} file(s)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python download_telegram.py <telegram_message_link>")
        sys.exit(1)
    main(sys.argv[1])