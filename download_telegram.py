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
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def download(url, path):

    r = requests.get(url, stream=True)

    if r.status_code == 200:

        with open(path, "wb") as f:

            for chunk in r.iter_content(1024):
                f.write(chunk)

        print("✅ Downloaded:", path)

    else:
        print("❌ Failed:", url)


def main(link):

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # enable network logs
    options.set_capability("goog:loggingPrefs", {
        "performance": "ALL"
    })

    service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(
        service=service,
        options=options
    )

    embed_url = link + "?embed=1&mode=tme"

    print("🌐 Opening:", embed_url)

    driver.get(embed_url)

    time.sleep(10)

    folder = clean_filename(
        link.replace("https://", "").replace("/", "_")
    )

    os.makedirs(folder, exist_ok=True)

    found = False

    # -------------------------
    # CLICK VIDEO IF EXISTS
    # -------------------------

    try:

        video = driver.find_element(By.TAG_NAME, "video")

        driver.execute_script("""
            arguments[0].play();
        """, video)

        print("▶️ Video playback triggered")

        time.sleep(5)

    except Exception:
        pass

    # -------------------------
    # READ NETWORK LOGS
    # -------------------------

    logs = driver.get_log("performance")

    media_urls = set()

    for entry in logs:

        try:

            message = json.loads(entry["message"])

            message = message["message"]

            if message["method"] != "Network.responseReceived":
                continue

            response = message["params"]["response"]

            url = response.get("url", "")

            mime = response.get("mimeType", "")

            # detect real media
            if (
                ".mp4" in url
                or "video" in mime
            ):

                media_urls.add(url)

        except Exception:
            continue

    # -------------------------
    # DOWNLOAD VIDEOS
    # -------------------------

    count = 0

    for url in media_urls:

        count += 1
        found = True

        print("🎬 Found media:", url)

        download(
            url,
            os.path.join(folder, f"video_{count}.mp4")
        )

    # -------------------------
    # CAPTION
    # -------------------------

    try:

        caption = driver.find_element(
            By.CLASS_NAME,
            "tgme_widget_message_text"
        ).text

        with open(
            os.path.join(folder, "caption.txt"),
            "w",
            encoding="utf-8"
        ) as f:

            f.write(caption)

        print("📝 Caption saved")

    except Exception:
        print("⚠️ No caption found")

    driver.quit()

    if not found:
        print("❌ No video/media found")


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("Usage: python download_telegram.py <link>")
        sys.exit(1)

    main(sys.argv[1])
