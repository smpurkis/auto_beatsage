import threading
import time
from pathlib import Path

import regex as re
from kivy.app import App
from kivy.config import Config
from kivy.core.window import Window
from kivy.lang.builder import Builder
from kivy.uix.button import Button
# from kivymd.uix.button import MDFillRoundFlatButton as Button
from kivy.uix.gridlayout import GridLayout
# from kivymd.app import MDApp as App
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from auto_beatsage_gui_version import async_upload_levels_to_quest, async_get_details, async_get_levels, get_song_urls, \
    get_sanitized_filename, commit_to_quest

Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

Builder.load_string('''
<WrapButton>:
    halign: "center"
    font_size: 15
    text_size : self.width, None
    height: 40
    size_hint_y: None
<WrapSpinner>:
    sync_height: True
    halign: "center"
    font_size: 15
    height: 40
    text_size : self.width, None
    height: self.texture_size[1]
''')


class WrapButton(Button):
    pass


class WrapSpinner(Spinner):
    def __init__(self, **kwargs):
        self.level_path = None
        self.status = kwargs.get("status", None)
        self.details = kwargs.get("details", None)
        self.title = kwargs.get("title", None)
        kwargs.pop("status")
        kwargs.pop("details")
        kwargs.pop("title")
        super().__init__(**kwargs)


class GUI(App):
    def build(self):
        # self.theme_cls.theme_style = "Dark"
        print(Path("images", "cat_loader.gif").absolute().__str__())
        assert Path("images", "cat_loader.gif").exists()
        self.loading_gif = AsyncImage(source=Path("images", "cat_loader.gif").__str__(),
                                      anim_delay=0.03,
                                      mipmap=True)
        self.popup = None

        self.main_layout = GridLayout(cols=2)

        self.songs = {}
        self.quest_local_ip = None

        self.lhs = GridLayout(cols=1)
        self.textinput = TextInput(hint_text='Please enter Soundcloud and/or YouTube playlists/songs ', multiline=True,
                                   size_hint_x=0.7,
                                   # background_color=(0, 0, 0, 0),
                                   # foreground_color=(0.3, 0.4, 0.5, 1)
                                   )
        self.lhs.add_widget(self.textinput)

        self.ip_input = TextInput(hint_text='Please enter Quest IP', multiline=False, size_hint_y=0.08)

        self.lhs.add_widget(self.ip_input)
        self.ip_input.bind(on_text_validate=self.get_ip)
        self.main_layout.add_widget(self.lhs)

        self.rhs = GridLayout(cols=1, size_hint_y=None)
        self.rhs.bind(minimum_height=self.rhs.setter('height'))

        get_details_btn = WrapButton(text="Get song details")
        get_details_btn.bind(on_press=self.details_thread)
        self.rhs.add_widget(get_details_btn)

        get_levels_btn = WrapButton(text="Get song beatsage levels")
        get_levels_btn.bind(on_press=self.levels_thread)
        self.rhs.add_widget(get_levels_btn)

        upload_commit_btn = WrapButton(text="Upload and commit levels")
        upload_commit_btn.bind(on_press=self.upload_commit_thread)
        self.rhs.add_widget(upload_commit_btn)

        root = ScrollView(size_hint=(1, None), size=(Window.width, Window.height))
        root.add_widget(self.rhs)
        self.main_layout.add_widget(root)

        return self.main_layout

    def get_ip(self, instance):
        ip_pat = re.compile(r"^(\d{3}\.\d{3}\.\d+\.\d+)$")
        text = instance.text
        check_ip = re.match(ip_pat, text)
        if check_ip:
            self.quest_local_ip = text
        else:
            popup = Popup(title='Warning',
                          content=Label(text='Incorrect IP input.\n Please enter a valid lan IP'),
                          size_hint=(None, None), size=(400, 200))
            popup.open()

    def show_selected_value(self, spinner, text):
        spinner.text = self.spinner_text
        print('The spinner', spinner, 'has text', text)

    def get_text(self, instance, text):
        self.spinner_text = instance.text
        print(self.spinner_text)

    def details_thread(self, instance):
        threading.Thread(None, target=self.get_details).start()

    def loading_popup(self, title="Loading"):
        if self.popup is None:
            self.popup = Popup(title=title,
                               content=self.loading_gif,
                               size_hint=(None, None), size=(400, 200))
            self.popup.bind(on_press=self.popup.dismiss)
        else:
            self.popup.title = title
        self.popup.open()

    def get_details(self):
        self.loading_popup(title="Loading Song Details")
        song_urls = self.textinput.text.split("\n")
        self.song_urls = get_song_urls(song_urls)
        print(self.song_urls)
        details = async_get_details(tuple(self.song_urls))
        for det in details:
            spinner = WrapSpinner(
                status="Details Received",
                details=det,
                title=det.get("title"),
                text=det.get("title"),
                values=(f"Artist: {det.get('author') if det.get('author') is not None else 'Unable to determine'}",
                        f'Uploader: {det.get("uploader")}',
                        f'Platform: {det.get("extractor")}',
                        f'View Count: {det.get("view_count")}',
                        f'Like Count: {det.get("like_count")}',),
                size_hint_y=None, height=40, background_color=[1, 0, 0, 1])
            if det.get("title") not in self.songs.keys():
                self.songs[det.get("title")] = spinner
                spinner.bind(on_touch_down=self.get_text)
                spinner.bind(text=self.show_selected_value)
                self.rhs.add_widget(spinner)
        self.check_status()
        self.popup.dismiss()

    def check_status(self, completed=False):
        for song in self.songs.values():
            if completed:
                self.songs.get(song.title).status = "Level Synced"
                self.songs.get(song.title).background_color = [0, 1, 0, 1]
            else:
                level_file = Path("levels", get_sanitized_filename(song.title))
                if level_file.exists() and level_file.is_file():
                    self.songs.get(song.title).status = "Level Downloaded"
                    self.songs.get(song.title).background_color = [1, 0.65, 0, 1]
                    self.songs.get(song.title).level_path = level_file

    def levels_thread(self, instance):
        threading.Thread(None, target=self.get_levels).start()

    def get_levels(self):
        self.loading_popup("Downloading Levels (will take 2-5 minutes per song)")
        details = [song.details for song in self.songs.values() if song.status == "Details Received"]
        level_paths = async_get_levels(self.song_urls, details)
        for d in level_paths:
            title = list(d.keys())[0]
            level_path = d[title]
            self.songs[title].level_path = level_path
        self.check_status()
        self.popup.dismiss()

    def upload_commit_thread(self, instance):
        if self.quest_local_ip is None:
            popup = Popup(title='Warning',
                          content=Label(text='No Oculus Quest IP address input.\n Please enter IP address.'),
                          size_hint=(None, None), size=(400, 200))
            popup.open()
        else:
            threading.Thread(None, target=self.upload_commit).start()

    def upload_commit(self):
        self.loading_popup("Committing to Quest")
        level_paths = [song.level_path for song in self.songs.values() if
                       song.status in ["Level Downloaded", "Level Synced"]]
        async_upload_levels_to_quest(level_paths, quest_local_ip=self.quest_local_ip)
        time.sleep(1)
        commit_to_quest(self.quest_local_ip)
        self.check_status(completed=True)
        self.popup.dismiss()


if __name__ == '__main__':
    GUI().run()
