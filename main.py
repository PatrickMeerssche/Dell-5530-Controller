#!/bin/python
import os
import sys

from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QApplication, QMenu

from main_window import MainWindow
from tray import TrayIcon


if __name__ == '__main__':
    # Create the Qt Application
    app = QApplication(sys.argv)
    app.setDesktopFileName("dell-g-series-controller")
    icon_path = os.path.join(os.path.dirname(__file__), "alien-square.png")
    icon = QIcon(icon_path)
    if icon.isNull():
        icon = QIcon(os.path.join(os.path.dirname(__file__), "alien-square.ico"))
    if icon.isNull():
        icon = QIcon.fromTheme("alienarena")
    app.setWindowIcon(icon)
    app.setQuitOnLastWindowClosed(False)

    # Create and show the window
    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    # Add item on the system tray
    tray = TrayIcon(window)
    window.tray = tray
    tray.setIcon(icon)
    tray.setVisible(True)
    tray.setToolTip("Right click to see the menu. Left click to toggle leds.")

    # System tray options
    menu = QMenu()
    show = QAction("Show Window")
    quit = QAction("Quit")
    menu.addAction(show)
    menu.addAction(quit)
    # Adding options to the System Tray
    tray.setContextMenu(menu)

    # Register callbacks
    quit.triggered.connect(app.quit)
    show.triggered.connect(window.show)

    # Run the main Qt loop
    sys.exit(app.exec())
