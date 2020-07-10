import asyncio
import json
from pathlib import Path

import aiohttp
import requests
from pathvalidate import sanitize_filename
from sclib import SoundcloudAPI
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from youtube_search import YoutubeSearch
import time

quest_local_ip = Path("settings.txt").read_text()


# Beatsage download functions
def get_soundcloud_playlist(playlist_url):
    api = SoundcloudAPI()
    print(playlist_url)
    rp = api.resolve(playlist_url)
    if "track" in str(type(rp)).lower():
        return [rp.permalink_url]
    else:
        soundcloud_urls = [track.permalink_url for track in rp.tracks]
    return soundcloud_urls


def get_song_url(url):
    if "youtube" in url:
        return [url]
    else:
        return get_soundcloud_playlist(url)


def get_youtube_url(search_query):
    results = YoutubeSearch(search_query, max_results=10).to_dict()
    if len(results) == 0:
        return
    link = results[0].get("link")
    youtube_url = f"https://www.youtube.com{link}"
    return youtube_url


async def download_url(sess, url, save_path, chunk_size=128):
    r = await sess.get(url)
    print(r, "Beginning download")
    assert r.status == 200
    with save_path.open("wb") as fd:
        while True:
            chunk = await r.content.read(chunk_size)
            if not chunk:
                break
            fd.write(chunk)
    print(f"Level saved at: {save_path}")


async def get_details(sess, url):
    print(f"Beginning download of {url}")

    data = {"youtube_url": url}
    rp = await sess.post("https://beatsage.com/youtube_metadata", data=json.dumps(data))
    if rp.status == 429:
        seconds_to_wait = 120
        print(f"Too many requests detected, waiting {seconds_to_wait} seconds")
        time.sleep(seconds_to_wait)
        rp = await sess.post("https://beatsage.com/youtube_metadata", data=json.dumps(data))
    assert rp.status == 200
    video_metadata = json.loads(await rp.text())

    video_metadata.get("title")
    return video_metadata


async def get_level(sess, url, upload=False):
    video_metadata = await get_details(sess, url)

    fields = {"youtube_url": url,
              "cover_art": "(binary)",
              "audio_metadata_title": video_metadata.get("title"),
              "audio_metadata_artist": video_metadata.get("artist"),
              "difficulties": "Hard,Expert,ExpertPlus,Normal",
              "modes": "Standard,90Degree,OneSaber",
              "events": "DotBlocks,Obstacles",
              "environment": "DefaultEnvironment",
              "system_tag": "v2"}
    data = aiohttp.FormData()
    for key in fields.keys():
        data.add_field(name=key, value=fields.get(key))
    rp = await sess.post("https://beatsage.com/beatsaber_custom_level_create", data=data)
    assert rp.status == 200

    content = json.loads(await rp.text())
    download_id = content.get("id")
    still_pending = True
    print("Pending level download")
    while still_pending:
        await asyncio.sleep(30)
        rp = await sess.get(f"https://beatsage.com/beatsaber_custom_level_heartbeat/{download_id}")
        assert rp.status == 200
        content = json.loads(await rp.text())
        status = content.get("status")
        if status.lower() == "done":
            break


    filename = sanitize_filename(f"{video_metadata.get('title')}_by_{video_metadata.get('artist')}".replace(" ", "_"))
    if len(filename) > 150:
        filename = filename[:150]
    filename = filename + ".zip"
    download_path = Path("levels", filename)
    await download_url(sess, f"https://beatsage.com/beatsaber_custom_level_download/{download_id}", download_path)
    if upload:
        file_path = Path(download_path)
        await upload_to_quest(sess, file_path)
    return download_path


async def upload_to_quest(sess, file_path):
    assert file_path.exists() and file_path.is_file()

    client_exceptions = (
        aiohttp.ClientResponseError,
        aiohttp.ClientConnectionError,
        aiohttp.ClientPayloadError,
        asyncio.TimeoutError,
    )
    while True:
        try:
            r = await sess.get(f"http://{quest_local_ip}:50000/main/upload")
            break
        except client_exceptions:
            print("Trying to find Quest to upload to")
            await asyncio.sleep(10)

    options = Options()
    options.headless = True
    driver = webdriver.Chrome(executable_path="/usr/bin/chromedriver", options=options)

    driver.get(f"http://{quest_local_ip}:50000/main/upload")
    driver.find_element(By.CSS_SELECTOR, "input").send_keys(file_path.absolute().__str__())
    WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".toast-message")))
    driver.find_element(By.CSS_SELECTOR, ".toast-message").click()
    print("Finished upload")
    driver.quit()


# Quest upload functions
def commit_to_quest(quest_local_ip):
    print("Starting commit")
    rp = requests.post(f"http://{quest_local_ip}:50000/host/beatsaber/commitconfig")
    assert rp.ok


async def run_tasks(song_urls):
    connector = aiohttp.TCPConnector(limit_per_host=2, limit=3)
    sess = aiohttp.ClientSession(connector=connector)
    semaphore = asyncio.Semaphore(5)
    async with semaphore:
        tasks = [get_level(sess, url, upload=True) for url in song_urls]
        for task in tasks:
            print(task)
        await asyncio.gather(*tasks)
    await sess.close()


def main():
    urls = Path("urls.txt").read_text().split("\n")
    song_urls = [get_song_url(url) for url in urls]
    song_urls = [y for x in song_urls for y in x]
    for url in song_urls:
        print(url)
    quest_local_ip = Path("settings.txt").read_text()
    loop = asyncio.get_event_loop()

    loop.run_until_complete(run_tasks(song_urls))
    commit_to_quest(quest_local_ip=quest_local_ip)


if __name__ == "__main__":
    main()
