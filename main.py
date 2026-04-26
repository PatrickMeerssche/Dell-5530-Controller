#!/bin/python
import os
import sys
import pexpect
import awelc
from PySide6.QtCore import (QSettings, QTimer, Qt)
from PySide6.QtGui import (QIcon, QAction, QColor)
from PySide6.QtWidgets import (QMessageBox, QGridLayout, QGroupBox, QWidget, QPushButton, QApplication,
                               QVBoxLayout, QHBoxLayout, QSlider, QLabel, QSystemTrayIcon, QMenu, QComboBox,
                               QCheckBox,
                               QColorDialog)

# User-facing mode labels are also persisted in settings.
MODE_STATIC = "Static Color"
MODE_MORPH = "Morph"
MODE_OFF = "Off"
LED_MODES = [MODE_STATIC, MODE_MORPH, MODE_OFF]

# awelc dim scale is inverse: 0 is brightest, higher values are dimmer.
BRIGHTNESS_LOW = "Low"
BRIGHTNESS_MEDIUM = "Medium"
BRIGHTNESS_HIGH = "High"
BRIGHTNESS_LEVELS = [BRIGHTNESS_LOW, BRIGHTNESS_MEDIUM, BRIGHTNESS_HIGH]
BRIGHTNESS_DIM_MAP = {
    BRIGHTNESS_LOW: 70,
    BRIGHTNESS_MEDIUM: 35,
    BRIGHTNESS_HIGH: 0,
}

CLOSE_EXIT = "Exit"
CLOSE_TRAY = "Minimize to Tray"
CLOSE_BEHAVIORS = [CLOSE_EXIT, CLOSE_TRAY]


class LedService:
    # Thin wrapper around low-level awelc calls to keep UI code decoupled.

    def set_static(self, red, green, blue):
        awelc.set_static(red, green, blue)

    def set_morph(self, red, green, blue, duration):
        awelc.set_morph(red, green, blue, duration)

    def remove_animation(self):
        awelc.remove_animation()

    def set_dim(self, level):
        awelc.set_dim(level)


class AcpiService:
    # Encapsulates privileged shell communication and ACPI argument templating.

    def __init__(self, shell, acpi_cmd, acpi_call_dict):
        self.shell = shell
        self.acpi_cmd = acpi_cmd
        self.acpi_call_dict = acpi_call_dict

    def shell_exec(self, cmd: str):
        print("Bash: Executing {}".format(cmd))
        self.shell.sendline(cmd)
        self.shell.expect("[#$] ")
        result = self.shell.before
        result = result.split('\n')
        for line in result[1:]:
            print(line)
        return result

    def parse_shell_exec(self, line: str):
        return line[line.find('\r') + 1:line.find('\x00')]

    def call(self, cmd, arg1="0x00", arg2="0x00"):
        args = self.acpi_call_dict[cmd]
        if len(args) == 4:
            cmd_current = self.acpi_cmd.format(args[0], args[1], args[2], args[3])
        elif len(args) == 3:
            cmd_current = self.acpi_cmd.format(args[0], args[1], args[2], arg1)
        elif len(args) == 2:
            cmd_current = self.acpi_cmd.format(args[0], args[1], arg1, arg2)
        else:
            cmd_current = ""
        return self.parse_shell_exec(self.shell_exec(cmd_current)[2])

class MainWindow(QWidget):

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.is_supported_5530 = False
        self.is_keyboard_supported = True # True by default, in case of no root access, keyboard lights should be adjustable.
        self.model_detection_status = "Unknown"
        self.root_status = "Unknown"
        self.acpi_status = "Unknown"
        self.last_acpi_response = "None"
        self.last_led_status = "Idle"
        self.startup_status = "Initializing..."
        self.led_service = LedService()

        # Prefer a shared log file, then fallback to a per-user path if needed.
        self.logfile = None
        log_candidates = [
            "/tmp/dell-g-series-controller.log",
            "/tmp/dell-g-series-controller-{}.log".format(os.getuid()),
        ]
        for log_path in log_candidates:
            try:
                self.logfile = open(log_path, "a", buffering=1)
                break
            except OSError:
                continue

        if self.logfile is not None:
            sys.stdout = self.logfile
            print("Log file:{}".format(self.logfile.name))
        else:
            print("Warning: could not open a log file under /tmp; continuing without file logging")

        # ACPI/root capability detection runs before building UI so unsupported
        # controls can be hidden on first render.
        self.init_acpi_call()
        self.setMinimumWidth(760)
        self.setMinimumHeight(560)
        self.setWindowTitle("Dell G Series Controller")
        self._apply_theme()
        # Read last choices from QSettings
        self.settings = QSettings('Dell-G15', 'Controller')
        #Create grid layout
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setContentsMargins(20, 20, 20, 20)

        self.timer = None
        grid.addWidget(self._create_first_exclusive_group(), 0, 0)
        if (self.is_root and self.is_supported_5530):
            grid.addWidget(self._create_second_exclusive_group(), 0, 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            self.timer = QTimer(self)    #timer to update fan rpm values
            self.timer.setInterval(1000)
            self.timer.timeout.connect(self.get_rpm_and_temp)
            self.timer.start()
        else:
            grid.setColumnStretch(0, 1)

        self.diagnostics_group = self._create_diagnostics_group()
        grid.addWidget(self.diagnostics_group, 1, 0, 1, 2)
        self.setLayout(grid)
        self._refresh_diagnostics()

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget {
                background: #000000;
                color: #f2f2f2;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #f2f2f2;
                border-radius: 12px;
                margin-top: 14px;
                padding: 16px 12px 12px 12px;
                font-weight: 700;
                background-color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #ffffff;
            }
            QComboBox, QPushButton {
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid #ffffff;
                background-color: #050505;
                padding: 4px 10px;
            }
            QComboBox:hover, QPushButton:hover {
                border-color: #66ccff;
                background-color: #0f0f0f;
            }
            QPushButton {
                background-color: #111111;
                border-color: #66ccff;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1b1b1b;
            }
            QSlider::groove:horizontal {
                height: 8px;
                border-radius: 4px;
                background: #1a1a1a;
            }
            QSlider::sub-page:horizontal {
                border-radius: 4px;
                background: #66ccff;
            }
            QSlider::handle:horizontal {
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: #ffffff;
                border: 1px solid #000000;
            }
            QLabel#previewLabel {
                border: 1px solid #ffffff;
                border-radius: 8px;
                min-height: 30px;
                font-weight: 600;
                color: #000000;
                padding: 4px 8px;
            }
            QLabel#colorCircle {
                border: 2px solid #ffffff;
                border-radius: 32px;
                min-width: 64px;
                max-width: 64px;
                min-height: 64px;
                max-height: 64px;
                background: #ffffff;
            }
        """)

    def _set_led_label_values(self):
        profile = self._duration_profile(self.duration.value())
        self.duration_label.setText(f"Duration ({self.duration.value()}) - {profile}")

    def _duration_profile(self, value):
        if value < 256:
            return "Very Fast"
        if value < 1024:
            return "Fast"
        if value < 2048:
            return "Balanced"
        if value < 3072:
            return "Slow"
        return "Very Slow"

    def _update_color_previews(self):
        static_rgb = (self.static_red, self.static_green, self.static_blue)
        static_hex = '#{:02X}{:02X}{:02X}'.format(*static_rgb)
        self.static_value_label.setText(f"Static: {static_hex}")
        self.static_circle.setStyleSheet(f"background-color: {static_hex}; border: 2px solid #ffffff; border-radius: 32px;")

    def _get_morph_rgb(self):
        # Morph effect works best with one channel maxed and others at zero.
        return (255, 0, 0)

    def _open_static_color_picker(self):
        current_color = QColor(self.static_red, self.static_green, self.static_blue)
        color = QColorDialog.getColor(
            current_color,
            self,
            "Pick Static Color",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if color.isValid():
            self.static_red = color.red()
            self.static_green = color.green()
            self.static_blue = color.blue()
            self._update_color_previews()
            self._mark_led_dirty()

    def _create_diagnostics_group(self):
        group = QGroupBox("Diagnostics")
        layout = QVBoxLayout()
        layout.setSpacing(6)
        self.diag_startup_label = QLabel("")
        self.diag_model_label = QLabel("")
        self.diag_root_label = QLabel("")
        self.diag_acpi_label = QLabel("")
        self.diag_last_acpi_label = QLabel("")
        self.diag_last_led_label = QLabel("")
        for label in (
            self.diag_startup_label,
            self.diag_model_label,
            self.diag_root_label,
            self.diag_acpi_label,
            self.diag_last_acpi_label,
            self.diag_last_led_label,
        ):
            label.setWordWrap(True)
            layout.addWidget(label)
        group.setLayout(layout)
        return group

    def _refresh_diagnostics(self):
        if not hasattr(self, "diag_startup_label"):
            return
        # Keep all startup/runtime statuses centralized in one panel.
        self.diag_startup_label.setText(f"Startup: {self.startup_status}")
        self.diag_model_label.setText(f"Model: {self.model_detection_status}")
        self.diag_root_label.setText(f"Root: {self.root_status}")
        self.diag_acpi_label.setText(f"ACPI: {self.acpi_status}")
        self.diag_last_acpi_label.setText(f"Last ACPI response: {self.last_acpi_response}")
        self.diag_last_led_label.setText(f"Last LED operation: {self.last_led_status}")

    def _get_close_behavior(self):
        close_behavior = self.settings.value("Close Behavior", CLOSE_EXIT)
        return close_behavior if close_behavior in CLOSE_BEHAVIORS else CLOSE_EXIT

    def _set_close_behavior(self, *_):
        self.settings.setValue("Close Behavior", self.close_behavior_choice.currentText())

    def _get_current_led_state(self):
        # Build a comparable snapshot from the currently visible LED controls.
        mode = self.combobox_mode.currentText()
        if mode == MODE_STATIC:
            return {
                "Action": MODE_STATIC,
                "Red Static": self.static_red,
                "Green Static": self.static_green,
                "Blue Static": self.static_blue,
                "Brightness": self.brightness_choice.currentText(),
            }
        if mode == MODE_MORPH:
            red_morph, green_morph, blue_morph = self._get_morph_rgb()
            return {
                "Action": MODE_MORPH,
                "Red Morph": red_morph,
                "Green Morph": green_morph,
                "Blue Morph": blue_morph,
                "Duration": self.duration.value(),
                "Brightness": self.brightness_choice.currentText(),
            }
        return {"Action": MODE_OFF}

    def _get_saved_led_state(self):
        # Build the equivalent snapshot from persisted settings.
        mode = self.combobox_mode.currentText()
        if mode == MODE_STATIC:
            return {
                "Action": self.settings.value("Action", MODE_STATIC),
                "Red Static": int(self.settings.value("Red Static", 122)),
                "Green Static": int(self.settings.value("Green Static", 122)),
                "Blue Static": int(self.settings.value("Blue Static", 122)),
                "Brightness": self.settings.value("Brightness", BRIGHTNESS_HIGH),
            }
        if mode == MODE_MORPH:
            return {
                "Action": self.settings.value("Action", MODE_STATIC),
                "Red Morph": int(self.settings.value("Red Morph", 255)),
                "Green Morph": int(self.settings.value("Green Morph", 0)),
                "Blue Morph": int(self.settings.value("Blue Morph", 0)),
                "Duration": int(self.settings.value("Duration", 255)),
                "Brightness": self.settings.value("Brightness", BRIGHTNESS_HIGH),
            }
        return {"Action": self.settings.value("Action", MODE_STATIC)}

    def _brightness_to_dim(self, brightness):
        return BRIGHTNESS_DIM_MAP.get(brightness, BRIGHTNESS_DIM_MAP[BRIGHTNESS_HIGH])

    def _is_device_missing_error(self, err):
        return "No supported device was found" in str(err)

    def _apply_brightness(self):
        brightness = self.brightness_choice.currentText()
        self.led_service.set_dim(self._brightness_to_dim(brightness))

    def _apply_saved_led_action(self):
        action = self.settings.value("Last Action", self.settings.value("Action", MODE_STATIC))
        brightness = self.settings.value("Brightness", BRIGHTNESS_HIGH)

        if action == MODE_MORPH:
            red_morph = int(self.settings.value("Red Morph", 255))
            green_morph = int(self.settings.value("Green Morph", 0))
            blue_morph = int(self.settings.value("Blue Morph", 0))
            duration = int(self.settings.value("Duration", 255))
            self.led_service.set_morph(red_morph, green_morph, blue_morph, duration)
            self.settings.setValue("Action", MODE_MORPH)
        else:
            red_static = int(self.settings.value("Red Static", 122))
            green_static = int(self.settings.value("Green Static", 122))
            blue_static = int(self.settings.value("Blue Static", 122))
            self.led_service.set_static(red_static, green_static, blue_static)
            self.settings.setValue("Action", MODE_STATIC)

        self.led_service.set_dim(self._brightness_to_dim(brightness))

    def _refresh_apply_button_state(self):
        # Enable Apply only when current UI selections diverge from saved values.
        self.button_apply.setEnabled(self._get_current_led_state() != self._get_saved_led_state())

    def _mark_led_dirty(self):
        self._refresh_apply_button_state()

    def _refresh_led_controls(self):
        mode = self.combobox_mode.currentText()
        static_visible = mode == MODE_STATIC
        duration_visible = mode == MODE_MORPH

        for widget in (self.static_picker_button, self.static_circle, self.static_value_label):
            widget.setVisible(static_visible)
        self.duration_label.setVisible(duration_visible)
        self.duration.setVisible(duration_visible)

        if mode == MODE_OFF:
            self.info_led_label.setText("LEDs are disabled. Click Apply to remove animation.")
        elif mode == MODE_STATIC:
            self.info_led_label.setText("Pick a color from the palette, then click Apply.")
        elif mode == MODE_MORPH:
            self.info_led_label.setText("Set duration and click Apply.")
        self._refresh_apply_button_state()

    def init_acpi_call(self):
        # ACPI command IDs known to work on the targeted Dell G15 5530 firmware.
        self.root_status = "Checking"
        self.acpi_status = "Unavailable"
        self.startup_status = "Starting privileged shell"
        self.power_modes_dict = {
            "USTT_Balanced" : "0xa0",
            "USTT_Performance" : "0xa1",
            "USTT_Quiet" : "0xa3",
            "USTT_BatterySaver" : "0xa5",
            "G Mode" : "0xab",
            "Manual" : "0x0",
        }
            
        self.acpi_call_dict = {
            "get_laptop_model" : ["0x1a", "0x02", "0x02"],
            "get_power_mode" : ["0x14", "0x0b", "0x00"],
            "set_power_mode" : ["0x15", "0x01"],    #To be used with a parameter
            "toggle_G_mode" : ["0x25", "0x01"],
            "get_G_mode" : ["0x25", "0x02"],
            "set_fan1_boost" : ["0x15", "0x02", "0x32"],            #To be used with a parameter
            "get_fan1_boost" : ["0x14", "0x0c", "0x32"],
            "get_fan1_rpm" : ["0x14", "0x05", "0x32"],
            "get_cpu_temp" : ["0x14", "0x04", "0x01"],
            "set_fan2_boost" : ["0x15", "0x02", "0x33"],            #To be used with a parameter
            "get_fan2_boost" : ["0x14", "0x0c", "0x33"],
            "get_fan2_rpm" : ["0x14", "0x05", "0x33"],
            "get_gpu_temp" : ["0x14", "0x04", "0x06"]
        }

        # Default ACPI command template used by this 5530-focused build.
        self.acpi_cmd = "echo \"\\_SB.AMWW.WMAX 0 {} {{{}, {}, {}, 0x00}}\" | tee /proc/acpi/call; cat /proc/acpi/call"

        def startup_shell_exec(cmd, timeout=8):
            # Local helper for startup steps with consistent error/status handling.
            try:
                print("Bash(startup): Executing {}".format(cmd))
                self.shell.sendline(cmd)
                self.shell.expect("[#$] ", timeout=timeout)
                result = self.shell.before.split('\n')
                for line in result[1:]:
                    print(line)
                return result
            except Exception as err:
                self.startup_status = f"Startup command failed: {cmd} ({err.__class__.__name__})"
                self.acpi_status = "Unavailable"
                self._refresh_diagnostics()
                return None

        print("Attempting to create elevated bash subprocess.")
        # Create a shell subprocess (root needed for power related functions)
        try:
            self.shell = pexpect.spawn('bash', encoding='utf-8', logfile=self.logfile, env=None, args=["--noprofile", "--norc"])
            self.shell.expect("[#$] ", timeout=8)
        except Exception as err:
            self.is_root = False
            self.root_status = "Denied"
            self.acpi_status = "Unavailable"
            self.startup_status = f"Shell startup failed: {err.__class__.__name__}"
            self._refresh_diagnostics()
            QMessageBox.warning(self, "Warning", "Cannot start shell for ACPI controls. Power functions will stay hidden.")
            return

        startup_shell_exec(" export HISTFILE=/dev/null; history -c")
        # Elevate privileges only when the process is not already root.
        if os.geteuid() != 0:
            if startup_shell_exec("pkexec bash --noprofile --norc") is None:
                self.is_root = False
                self.root_status = "Denied"
                self.startup_status = "pkexec denied or timed out"
                self._refresh_diagnostics()
                QMessageBox.warning(self, "Warning", "No root access. Power related functions will not work, and will not be displayed.")
                return

            startup_shell_exec(" export HISTFILE=/dev/null; history -c")
        #Check if root or not
        whoami = startup_shell_exec("whoami")
        self.is_root = bool(whoami and len(whoami) > 1 and whoami[1].find("root") != -1)
        if not self.is_root:
            print("Bash shell is NOT root. Disabling ACPI methods...")
            self.root_status = "Denied"
            self.acpi_status = "Unavailable"
            self.startup_status = "Root access denied"
            self._refresh_diagnostics()
            QMessageBox.warning(self,"Warning","No root access. Power related functions will not work, and will not be displayed.")
            return

        print("Sh shell is root. Enabling ACPI methods...")
        self.root_status = "OK"
        self.acpi_status = "Ready"
        self.startup_status = "Root shell ready"
        self.acpi_service = AcpiService(self.shell, self.acpi_cmd, self.acpi_call_dict)

        self._check_laptop_model()

        if self.is_supported_5530:
            print("Laptop model is supported (Dell G15 5530).")
            self.startup_status = "Root OK; model supported"
        else:
            self.startup_status = "Root OK; model not supported"
            QMessageBox.warning(self,"Unsupported laptop","This build is optimized for Dell G15 5530 only. Power and fan controls will stay hidden.")
        self._refresh_diagnostics()
    
    def _check_laptop_model(self):
        """Check whether the laptop is a Dell G15 5530."""

        try:
            laptop_model = self.acpi_call("get_laptop_model")
        except Exception as err:
            self.is_supported_5530 = False
            self.model_detection_status = f"Detection failed ({err.__class__.__name__})"
            self.acpi_status = "Unavailable"
            self.startup_status = "ACPI call failed during model detection"
            self._refresh_diagnostics()
            return

        if laptop_model == "0x0":
            print("Detected Dell G15 5530. Laptop model: {}".format(laptop_model))
            self.is_supported_5530 = True
            self.is_keyboard_supported = True
            self.model_detection_status = "Dell G15 5530"
        else:
            print("Non-5530 model signature detected: {}".format(laptop_model))
            self.is_supported_5530 = False
            self.model_detection_status = f"Unsupported signature {laptop_model}"
        self._refresh_diagnostics()

        
    def _create_first_exclusive_group(self):
        # Keyboard LED controls are always shown, even without root privileges.
        groupBox = QGroupBox("Keyboard Led")
        vbox = QVBoxLayout()
        vbox.setSpacing(8)
        if self.is_keyboard_supported:
            self.state = (self.settings.value("State", "Off"))
            self.static_red = int(self.settings.value("Red Static", 122))
            self.static_green = int(self.settings.value("Green Static", 122))
            self.static_blue = int(self.settings.value("Blue Static", 122))

            self.static_picker_button = QPushButton("Pick Static Color")
            self.static_circle = QLabel("")
            self.static_circle.setObjectName("colorCircle")
            self.static_value_label = QLabel("")

            self.brightness_label = QLabel("Brightness")
            self.brightness_choice = QComboBox()
            self.brightness_choice.addItems(BRIGHTNESS_LEVELS)
            saved_brightness = self.settings.value("Brightness", BRIGHTNESS_HIGH)
            self.brightness_choice.setCurrentText(saved_brightness if saved_brightness in BRIGHTNESS_LEVELS else BRIGHTNESS_HIGH)

            self.duration_label = QLabel("Duration")
            self.duration = QSlider(orientation=Qt.Orientation.Horizontal)
            self.duration.setMinimum(0x4)
            self.duration.setMaximum(0xfff)
            self.duration.setMinimumSize(100,0)
            self.duration.setValue(int(self.settings.value("Duration", 255)))

            static_widget = QWidget()
            static_hbox = QHBoxLayout(static_widget)
            static_hbox.setContentsMargins(0, 0, 0, 0)
            static_hbox.setSpacing(10)
            static_hbox.addWidget(self.static_circle)
            static_hbox.addWidget(self.static_picker_button)
            static_hbox.addStretch(1)

            widget = QWidget()
            hbox = QHBoxLayout(widget)
            hbox.setContentsMargins(0, 6, 0, 0)
            hbox.setSpacing(8)
            self.combobox_mode = QComboBox()
            self.combobox_mode.addItems(LED_MODES)
            saved_action = self.settings.value("Action", MODE_STATIC)
            self.combobox_mode.setCurrentText(saved_action if saved_action in LED_MODES else MODE_STATIC)

            self.button_apply = QPushButton("Apply")
            hbox.addWidget(self.combobox_mode)
            hbox.addWidget(self.button_apply)

            self.info_led_label = QLabel("")
            self.info_led_label.setWordWrap(True)

            # Add widgets to layout
            vbox.addWidget(static_widget)
            vbox.addWidget(self.static_value_label)
            vbox.addWidget(self.brightness_label)
            vbox.addWidget(self.brightness_choice)
            vbox.addWidget(self.duration_label)
            vbox.addWidget(self.duration)
            vbox.addWidget(self.info_led_label)
            vbox.addWidget(widget)

            self._set_led_label_values()
            self._update_color_previews()
            self._refresh_led_controls()

            self.duration.valueChanged.connect(self._set_led_label_values)
            self.duration.valueChanged.connect(self._mark_led_dirty)
            self.static_picker_button.clicked.connect(self._open_static_color_picker)
            self.brightness_choice.currentTextChanged.connect(self._mark_led_dirty)

            # Add button callbacks
            self.combobox_mode.currentTextChanged.connect(self.combobox_choice)
            self.button_apply.clicked.connect(self.apply_leds)

        else:
            label = QLabel("Keyboard support not currently available for this model")
            label.setWordWrap(True)
            vbox.addWidget(label)
        #Return
        groupBox.setLayout(vbox)
        return groupBox


    def _create_second_exclusive_group(self):
        # Power/fan controls require root and a supported model.
        groupBox = QGroupBox("Power and Fans")
        vbox = QVBoxLayout()
        vbox.setSpacing(10)
        
        widget = QWidget()
        hbox = QHBoxLayout(widget)
        
        #Power mode choice and Apply button
        self.combobox_mode_power = QComboBox()
        self.combobox_mode_power.addItems(self.power_modes_dict.keys())
        self.combobox_mode_power.setCurrentText(self.settings.value("Power", "USTT_Balanced"))
        self.info_label = QLabel("Select a power mode or adjust fan boost levels.")
        self.info_label.setWordWrap(True)

        self.live_fan_checkbox = QCheckBox("Apply fan boost while dragging")
        self.live_fan_checkbox.setChecked(self.settings.value("Live Fan Apply", "False") == "True")

        close_behavior_widget = QWidget()
        close_behavior_hbox = QHBoxLayout(close_behavior_widget)
        close_behavior_hbox.setContentsMargins(0, 0, 0, 0)
        close_behavior_hbox.setSpacing(8)
        close_behavior_hbox.addWidget(QLabel("Close action"))
        self.close_behavior_choice = QComboBox()
        self.close_behavior_choice.addItems(CLOSE_BEHAVIORS)
        self.close_behavior_choice.setCurrentText(self._get_close_behavior())
        close_behavior_hbox.addWidget(self.close_behavior_choice)
        
        #Fan 1 RPM
        self.fan1_label = QLabel("CPU Fan Boost")
        self.widget_fan1 = QWidget()
        hbox_fan1 = QHBoxLayout(self.widget_fan1)
        hbox_fan1.setContentsMargins(0, 0, 0, 0)
        hbox_fan1.setSpacing(8)
        self.fan1_boost = QSlider(orientation=Qt.Orientation.Horizontal)
        self.fan1_boost.setMinimum(0x00)
        self.fan1_boost.setMaximum(0xff)
        self.fan1_boost.setMinimumSize(100,0)
        self.fan1_boost.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fan1_boost.setTickInterval(25.5)   #10 steps
        self.fan1_boost.setValue(int(self.settings.value("Fan1 Boost", 0x00)))
        self.fan1_current = QLabel("0 RPM")
        hbox_fan1.addWidget(self.fan1_boost)
        hbox_fan1.addWidget(self.fan1_current)

        #Fan 2 RPM
        self.fan2_label = QLabel("GPU Fan Boost")
        self.widget_fan2 = QWidget()
        hbox_fan2 = QHBoxLayout(self.widget_fan2)
        hbox_fan2.setContentsMargins(0, 0, 0, 0)
        hbox_fan2.setSpacing(8)
        self.fan2_boost = QSlider(orientation=Qt.Orientation.Horizontal)
        self.fan2_boost.setMinimum(0x00)
        self.fan2_boost.setMaximum(0xff)
        self.fan2_boost.setMinimumSize(100,0)
        self.fan2_boost.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fan2_boost.setTickInterval(25.5)   #10 steps
        self.fan2_boost.setValue(int(self.settings.value("Fan2 Boost", 0x00)))
        self.fan2_current = QLabel("0 RPM")
        hbox_fan2.addWidget(self.fan2_boost)
        hbox_fan2.addWidget(self.fan2_current)

        self.fan1_live_timer = QTimer(self)
        self.fan1_live_timer.setSingleShot(True)
        self.fan1_live_timer.setInterval(150)
        self.fan1_live_timer.timeout.connect(self._apply_fan1_boost)

        self.fan2_live_timer = QTimer(self)
        self.fan2_live_timer.setSingleShot(True)
        self.fan2_live_timer.setInterval(150)
        self.fan2_live_timer.timeout.connect(self._apply_fan2_boost)

        #Add widgets to layout
        vbox.addWidget(self.combobox_mode_power)
        vbox.addWidget(self.fan1_label)
        vbox.addWidget(self.widget_fan1)
        vbox.addWidget(self.fan2_label)
        vbox.addWidget(self.widget_fan2)
        vbox.addWidget(self.live_fan_checkbox)
        vbox.addWidget(close_behavior_widget)
        vbox.addWidget(self.info_label)
        
        # Add button callbacks
        self.combobox_mode_power.currentTextChanged.connect(self.combobox_power)
        self.fan1_boost.sliderReleased.connect(self.slider_fan1)
        self.fan2_boost.sliderReleased.connect(self.slider_fan2)
        self.fan1_boost.valueChanged.connect(self._live_fan1_changed)
        self.fan2_boost.valueChanged.connect(self._live_fan2_changed)
        self.fan1_boost.valueChanged.connect(self._update_fan_boost_labels)
        self.fan2_boost.valueChanged.connect(self._update_fan_boost_labels)
        self.live_fan_checkbox.toggled.connect(self._set_live_fan_apply)
        self.close_behavior_choice.currentTextChanged.connect(self._set_close_behavior)

        self._update_fan_boost_labels()
        self._refresh_fan_controls_visibility()
        
        #Return
        groupBox.setLayout(vbox)
        return groupBox

    #Callbacks
    def combobox_choice(self):
        self._refresh_led_controls()


    def apply_leds(self):
        # Single entry point for mode-specific LED apply operations.
        try:
            mode = self.combobox_mode.currentText()
            if mode == MODE_STATIC:
                self.apply_static()
            elif mode == MODE_MORPH:
                self.apply_morph()
            else:   #Off
                self.remove_animation()
            self.info_led_label.setText("Applied successfully.")
            self.last_led_status = "Apply successful"
            self._refresh_diagnostics()
            self._refresh_apply_button_state()
        except Exception as err:
            self.info_led_label.setText(f"Apply failed: {err.__class__.__name__}")
            self.last_led_status = f"Apply failed: {err.__class__.__name__}"
            self._refresh_diagnostics()
            QMessageBox.warning(self,"Error",f"Cannot apply LED settings:\n\n{err.__class__.__name__}: {err}")
            raise err


    def combobox_power(self):
        # Power-mode changes reset manual fan sliders and then confirm via ACPI.
        self.fan1_boost.setValue(0)
        self.fan2_boost.setValue(0)
        self.settings.setValue("Power", self.combobox_mode_power.currentText())
        choice = self.settings.value("Power", "USTT_Balanced")
        message = ""
        
        # Set power mode
        mode = self.power_modes_dict[choice]
        self.acpi_call("set_power_mode",mode)
        # Get current power mode to confirm
        result = self.acpi_call("get_power_mode")
        if (result == mode):   #Expected result
            message = "Power mode set to {}.\n".format(choice)
        else:
            message = "Error! Command returned: {}, but expecting {}.\n".format(str(result),str(mode))
        # Get G Mode
        result = self.acpi_call("get_G_mode")
        if (choice == "G Mode") != (result == "0x1"):  #Toggle G Mode if needed.
            #Toggle G mode
            result_toggle = self.acpi_call("toggle_G_mode")
            if (("0x1" if choice == "G Mode" else "0x0") != result_toggle): 
                message = message + "Expected to read G Mode = {} but read {}!\n".format(choice == "G Mode",result_toggle)

        self.info_label.setText(message)
        self._refresh_fan_controls_visibility()
        self._refresh_diagnostics()

    def _refresh_fan_controls_visibility(self):
        is_manual = self.combobox_mode_power.currentText() == "Manual"
        self.fan1_label.setVisible(is_manual)
        self.widget_fan1.setVisible(is_manual)
        self.fan2_label.setVisible(is_manual)
        self.widget_fan2.setVisible(is_manual)
        self.live_fan_checkbox.setVisible(is_manual)

    def _set_live_fan_apply(self, *_):
        self.settings.setValue("Live Fan Apply", str(self.live_fan_checkbox.isChecked()))

    def _live_fan1_changed(self, *_):
        # Debounce writes while dragging to avoid flooding ACPI calls.
        if self.live_fan_checkbox.isChecked():
            self.fan1_live_timer.start()

    def _live_fan2_changed(self, *_):
        if self.live_fan_checkbox.isChecked():
            self.fan2_live_timer.start()

    def _update_fan_boost_labels(self, *_):
        fan1_percent = int(self.fan1_boost.value() / 0xff * 100)
        fan2_percent = int(self.fan2_boost.value() / 0xff * 100)
        self.fan1_label.setText(f"CPU Fan Boost ({fan1_percent}%)")
        self.fan2_label.setText(f"GPU Fan Boost ({fan2_percent}%)")


    def slider_fan1(self):
        if self.live_fan_checkbox.isChecked():
            return
        self._apply_fan1_boost()

    def _apply_fan1_boost(self):
        #Fan1 has id 0x32
        #Get current fan boost
        fan1_last_boost = self.acpi_call("get_fan1_boost")
        #Set new fan boost
        new_val = self.fan1_boost.value()
        self.acpi_call("set_fan1_boost","0x{:2X}".format(new_val))
        #Get current fan boost
        fan1_new_boost = self.acpi_call("get_fan1_boost")
        self.info_label.setText("Fan1 Boost: {:.0f}% to {:.0f}%.".format(int(fan1_last_boost,0)/0xff*100,int(fan1_new_boost,0)/0xff*100))
        self._refresh_diagnostics()


    def slider_fan2(self):
        if self.live_fan_checkbox.isChecked():
            return
        self._apply_fan2_boost()

    def _apply_fan2_boost(self):
        #Fan2 has id 0x33
        #Get current fan boost
        fan2_last_boost = self.acpi_call("get_fan2_boost")
        #Set new fan boost
        new_val = self.fan2_boost.value()
        self.acpi_call("set_fan2_boost","0x{:2X}".format(new_val))
        #Get current fan boost
        fan2_new_boost = self.acpi_call("get_fan2_boost")
        self.info_label.setText("Fan2 Boost: {:.0f}% to {:.0f}%.".format(int(fan2_last_boost,0)/0xff*100,int(fan2_new_boost,0)/0xff*100))
        self._refresh_diagnostics()


    def get_rpm_and_temp(self):
        if self.isVisible():
            #Get current rpm and temp
            fan1_rpm = self.acpi_call("get_fan1_rpm")
            cpu_temp = self.acpi_call("get_cpu_temp")
            fan2_rpm = self.acpi_call("get_fan2_rpm")
            gpu_temp = self.acpi_call("get_gpu_temp")
            self.fan1_current.setText("{} RPM, {} °C".format(int(fan1_rpm,0),int(cpu_temp,0)))
            self.fan2_current.setText("{} RPM, {} °C".format(int(fan2_rpm,0),int(gpu_temp,0)))
    # Helper Functions
    
    #Execute given command in elevated shell
    def acpi_call(self, cmd, arg1="0x00", arg2="0x00"):
        # Track last response for diagnostics panel visibility.
        result = self.acpi_service.call(cmd, arg1, arg2)
        self.last_acpi_response = f"{cmd}: {result}"
        return result


    def shell_exec(self, cmd : str):
        print("Bash: Executing {}".format(cmd))
        self.shell.sendline(cmd)
        self.shell.expect("[#$] ")
        result = self.shell.before
        result = result.split('\n')
        for line in result[1:]: #First line is the command that was sent
            print(line)
        return result


    def parse_shell_exec(self,line:str):
        return line[line.find('\r')+1:line.find('\x00')] #Read between carriage return and end of the line (disregard color)


    # Apply given colors to keyboard.
    def apply_static(self):
        # Program effect first, then dim, so brightness remains persistent.
        self.led_service.set_static(self.static_red, self.static_green,
                                    self.static_blue)
        self._apply_brightness()
        self.settings.setValue("Last Action", MODE_STATIC)
        self.settings.setValue("Action", MODE_STATIC)
        self.settings.setValue("Red Static", self.static_red)
        self.settings.setValue("Green Static", self.static_green)
        self.settings.setValue("Blue Static", self.static_blue)
        self.settings.setValue("Brightness", self.brightness_choice.currentText())
        self.settings.setValue("Duration", self.duration.value())
        self.settings.setValue("State", "On")
        self.last_led_status = "Static color applied"
        self._refresh_diagnostics()


    def apply_morph(self):
        # Program effect first, then dim, so brightness remains persistent.
        red_morph, green_morph, blue_morph = self._get_morph_rgb()
        self.led_service.set_morph(red_morph, green_morph,
                                   blue_morph, self.duration.value())
        self._apply_brightness()
        self.settings.setValue("Last Action", MODE_MORPH)
        self.settings.setValue("Action", MODE_MORPH)
        self.settings.setValue("Red Morph", red_morph)
        self.settings.setValue("Green Morph", green_morph)
        self.settings.setValue("Blue Morph", blue_morph)
        self.settings.setValue("Brightness", self.brightness_choice.currentText())
        self.settings.setValue("Duration", self.duration.value())
        self.settings.setValue("State", "On")
        self.last_led_status = "Morph applied"
        self._refresh_diagnostics()


    def remove_animation(self):
        try:
            self.led_service.remove_animation()
            self.last_led_status = "LED animation removed"
        except Exception as err:
            # Treat missing hardware as already-off when user requests Off.
            if self._is_device_missing_error(err):
                self.last_led_status = "LED device not found; treated as off"
            else:
                raise
        self.settings.setValue("Action", MODE_OFF)
        self.settings.setValue("State", "Off")
        self._refresh_diagnostics()

    # Apply last action when called from system tray
    def tray_on(self):
        # Tray toggle restores the previous non-Off mode and brightness.
        try:
            self._apply_saved_led_action()
            self.last_led_status = "Restored saved LED mode"
        except Exception as err:
            if not self._is_device_missing_error(err):
                raise
            self.last_led_status = "LED device not found; could not restore"
        self.settings.setValue("State", "On")
        self._refresh_diagnostics()

    def tray_off(self):
        # Full dim effectively turns keyboard lighting off.
        try:
            self.led_service.set_dim(100)
        except Exception as err:
            if not self._is_device_missing_error(err):
                raise
            self.last_led_status = "LED device not found; treated as off"
        self.settings.setValue("State", "Off")

    def closeEvent(self, event):
        # Respect user preference: minimize to tray or exit fully.
        if self._get_close_behavior() == CLOSE_TRAY:
            event.ignore()
            self.hide()
            return
        if hasattr(self, "tray"):
            self.tray.hide()
        event.accept()
        QApplication.quit()


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
