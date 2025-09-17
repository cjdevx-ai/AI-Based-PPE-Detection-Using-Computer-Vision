from kivy.app import App
from kivy.uix.image import Image
from kivy.uix.boxlayout import BoxLayout

class ImageApp(App):
    def build(self):
        layout = BoxLayout(orientation='vertical')
        img = Image(source='annotated_ppe_result.jpg')
        layout.add_widget(img)
        return layout

if __name__ == '__main__':
    ImageApp().run()
