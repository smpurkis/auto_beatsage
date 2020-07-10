import threading
import regex as re

# from kivy.app import App
from kivymd.app import MDApp as App
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.button import Button
# from kivymd.uix.button import MDFillRoundFlatButton as Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivymd.uix.textfield import MDTextField
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.metrics import dp
from kivy.lang.builder import Builder

from auto_beatsage_gui_version import async_get_details, async_get_levels, get_song_urls, commit_to_quest

Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

Builder.load_string('''
<WrapButton>:
    halign: "center"
    font_size: 15
    text_size : self.width, None
    height: 40
    size_hint_y: None
<WrapSpinner>:
    halign: "center"
    font_size: 15
    text_size : self.width, None
    height: self.texture_size[1]
''')


class WrapButton(Button):
    pass


class WrapSpinner(Spinner):
    def __init__(self, **kwargs):
        self.details = kwargs.get("details", None)
        self.title = kwargs.get("title", None)
        kwargs.pop("details")
        kwargs.pop("title")
        super().__init__(**kwargs)



class GUI(App):
    def build(self):
        self.theme_cls.theme_style = "Dark"

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

    def get_details(self):
        song_urls = self.textinput.text.split("\n")
        self.song_urls = get_song_urls(song_urls)
        print(self.song_urls)
        details = async_get_details(tuple(self.song_urls))
        for det in details:
            spinner = WrapSpinner(
                details=det,
                title=det.get("title"),
                text=det.get("title"),
                values=(f"Artist: {det.get('author') if det.get('author') is not None else 'Unable to determine'}",
                        f'Uploader: {det.get("uploader")}',
                        f'Platform: {det.get("extractor")}',
                        f'View Count: {det.get("view_count")}',
                        f'Like Count: {det.get("like_count")}'),
                size_hint_y=None, height=40)
            self.songs[det.get("title")] = spinner
            spinner.bind(on_touch_down=self.get_text)
            spinner.bind(text=self.show_selected_value)
            self.rhs.add_widget(spinner)

    def levels_thread(self, instance):
        threading.Thread(None, target=self.get_levels).start()

    def get_levels(self):
        details = [d for d in self.songs.values()]
        async_get_levels(self.song_urls, details)

    def upload_commit_thread(self, instance):
        if self.quest_local_ip is None:
            popup = Popup(title='Warning',
                          content=Label(text='No Oculus Quest IP address input.\n Please enter IP address.'),
                          size_hint=(None, None), size=(400, 200))
            popup.open()
        else:
            threading.Thread(None, target=self.get_levels).start()

    def upload_commit(self):
        commit_to_quest(quest_local_ip=self.quest_local_ip)


if __name__ == '__main__':
    GUI().run()
