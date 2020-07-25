import asyncio
import json
import time
from pathlib import Path

import httpx
import requests
from pathvalidate import sanitize_filename
from sclib import SoundcloudAPI


def get_sanitized_filename(title):
    filename = sanitize_filename(f"{title}".replace(" ", "_"))
    if len(filename) > 150:
        filename = filename[:150]
    filename = filename + ".zip"
    return filename


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
    if "youtube.com" in url:
        return [url]
    else:
        return get_soundcloud_playlist(url)


async def download_url(sess, url, save_path, chunk_size=128):
    async with sess.stream("get", url) as r:
        print(r, "Beginning download")
        assert r.status_code == 200
        with save_path.open("wb") as fd:
            async for chunk in r.aiter_bytes():
                if not chunk:
                    break
                fd.write(chunk)
        print(f"Level saved at: {save_path}")


async def get_details(sess, url):
    print(f"Getting details of: {url}")

    data = {"youtube_url": url}
    for i in range(3):
        rp = await sess.post("https://beatsage.com/youtube_metadata", data=json.dumps(data))
        if rp.status_code == 429:
            seconds_to_wait = 60
            print(f"Too many requests detected, waiting {seconds_to_wait} seconds")
            time.sleep(seconds_to_wait)
            rp = await sess.post("https://beatsage.com/youtube_metadata", data=json.dumps(data))
        if rp.status_code != 200:
            continue
        else:
            break
    video_metadata = json.loads(rp.text)

    video_metadata.get("title")
    return video_metadata


async def get_level(sess, video_data, upload=False):
    url = video_data[0]
    video_metadata = video_data[1]
    fields = {"youtube_url": url,
              "cover_art": "(binary)",
              "audio_metadata_title": video_metadata.get("title"),
              "audio_metadata_artist": video_metadata.get("artist"),
              "difficulties": "Hard,Expert,ExpertPlus,Normal",
              "modes": "Standard,90Degree,OneSaber",
              "events": "DotBlocks,Obstacles",
              "environment": "DefaultEnvironment",
              "system_tag": "v2"}
    data = fields
    # data = aiohttp.FormData()
    # for key in fields.keys():
    #     data.add_field(name=key, value=fields.get(key))
    rp = await sess.post("https://beatsage.com/beatsaber_custom_level_create", data=data)
    assert rp.status_code == 200

    content = json.loads(rp.text)
    download_id = content.get("id")
    still_pending = True
    print("Pending level download")
    while still_pending:
        await asyncio.sleep(30)
        rp = await sess.get(f"https://beatsage.com/beatsaber_custom_level_heartbeat/{download_id}")
        assert rp.status_code == 200
        content = json.loads(rp.text)
        status = content.get("status")
        if status.lower() == "done":
            break

    filename = get_sanitized_filename(video_metadata.get('title'))
    download_path = Path("levels", filename)
    level_folder = Path("levels")
    if not level_folder.exists():
        level_folder.mkdir()
    await download_url(sess, f"https://beatsage.com/beatsaber_custom_level_download/{download_id}", download_path)
    if upload:
        file_path = Path(download_path)
        await upload_to_quest(sess, file_path)
    return {video_metadata.get("title"): download_path}


async def upload_to_quest(sess, file_path, quest_local_ip):
    assert file_path.exists() and file_path.is_file()

    client_exceptions = (
        asyncio.TimeoutError,
        httpx.ConnectTimeout
    )
    while True:
        try:
            await sess.get(f"http://{quest_local_ip}:50000/main/upload")
            break
        except client_exceptions:
            print("Trying to find Quest to upload to")
            await asyncio.sleep(10)

    files = {"name": "file", "filename": file_path.name, "file": file_path.open("rb")}
    rp = await sess.post(f"http://{quest_local_ip}:50000/host/beatsaber/upload", files=files)
    assert rp.status_code == 204

    # options = Options()
    # options.headless = True
    # driver = webdriver.Chrome(executable_path="/usr/bin/chromedriver", options=options)
    #
    # driver.get(f"http://{quest_local_ip}:50000/main/upload")
    # driver.find_element(By.CSS_SELECTOR, "input").send_keys(file_path.absolute().__str__())
    # WebDriverWait(driver, 300).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".toast-message")))
    # driver.find_element(By.CSS_SELECTOR, ".toast-message").click()
    # print("Finished upload")
    # driver.quit()


# Quest upload functions
def commit_to_quest(quest_local_ip):
    print("Starting commit")
    rp = requests.post(f"http://{quest_local_ip}:50000/host/beatsaber/commitconfig")
    assert rp.ok


async def run_tasks(todo, function, **kwargs):
    # connector = aiohttp.TCPConnector(limit_per_host=2, limit=3)
    # sess = aiohttp.ClientSession(connector=connector)
    sess = httpx.AsyncClient(timeout=600)
    semaphore = asyncio.Semaphore(5)
    async with semaphore:
        tasks = [function(sess, elem, **kwargs) for elem in todo]
        for task in tasks:
            print(task)
        results = await asyncio.gather(*tasks)
    # await sess.close()
    return results


def get_song_urls(urls=None):
    if urls is None:
        urls = Path("urls.txt").read_text().split("\n")
    song_urls = [get_song_url(url) for url in urls]
    song_urls = [y for x in song_urls for y in x]
    for url in song_urls:
        print(url)
    return song_urls


def async_get_details(song_urls):
    # asyncio.set_event_loop(asyncio.new_event_loop())
    # loop = asyncio.get_event_loop()
    loop = asyncio.new_event_loop()
    video_metadatas = loop.run_until_complete(run_tasks(song_urls, get_details))
    return video_metadatas


def async_get_levels(song_urls, video_metadatas):
    loop = asyncio.new_event_loop()
    video_data_list = list(zip(song_urls, video_metadatas))
    download_paths = loop.run_until_complete(run_tasks(video_data_list, get_level, upload=False))
    return download_paths


def async_upload_levels_to_quest(level_paths, quest_local_ip):
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_tasks(level_paths, upload_to_quest, quest_local_ip=quest_local_ip))


def main():
    file_path = Path(
        "/home/sam/PycharmProjects/auto_beatsage/levels/Echo_(feat._Tauren_Wells)__Live__Elevation_Worship.zip")
    quest_local_ip = "192.168.1.38"
    files = {"name": "file", "filename": file_path.name, "file": file_path.open("rb")}
    rp = httpx.post(f"http://{quest_local_ip}:50000/host/beatsaber/upload", files=files)
    print(rp)


if __name__ == "__main__":
    main()
