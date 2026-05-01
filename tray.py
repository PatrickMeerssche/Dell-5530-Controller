from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QSystemTrayIcon


class TrayIcon(QSystemTrayIcon):
    # Handles tray click behavior and delegates LED toggling back to MainWindow.

    def __init__(self, window, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = QSettings('Dell-G15', 'Controller')
        self.state = (self.settings.value("State", "Off"))
        self.activated.connect(self.toggle_leds)
        self.window = window

    def toggle_leds(self, reason):
        if self.settings.value("State", "Off") == "Off":
            self.settings.setValue("State", "On")
            self.window.tray_on()
        else:
            self.settings.setValue("State", "Off")
            self.window.tray_off()
