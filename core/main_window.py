import os
import sys
import pexpect
from collections import deque

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QLabel,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from core.constants import (
    MODE_STATIC,
    MODE_MORPH,
    MODE_OFF,
    BRIGHTNESS_HIGH,
    CLOSE_EXIT,
    CLOSE_TRAY,
)
from core.services import LedService, AcpiService
from ui.led import LedPanelMixin
from ui.power import PowerPanelMixin
from ui.sensors import SensorsPanelMixin
from ui.diagnostics import DiagnosticsPanelMixin


class MainWindow(
    QWidget,
    LedPanelMixin,
    PowerPanelMixin,
    SensorsPanelMixin,
    DiagnosticsPanelMixin,
):

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.is_supported_5530 = False
        self.is_keyboard_supported = True # True by default, in case of no root access, keyboard lights should be adjustable.
        self.model_detection_status = "Unknown"
        self.root_status = "Unknown"
        self.acpi_status = "Unknown"
        self.last_acpi_response = "None"
        self.last_led_status = "Idle"
        self.led_version = "Unknown"
        self.startup_status = "Initializing..."
        self.led_service = LedService()
        # History buffers for small sparklines (120 samples ~= 60 seconds at 0.5s)
        self.cpu_history = deque(maxlen=120)
        self.gpu_history = deque(maxlen=120)
        self.last_sensor_values = None
        self.sparkline_redraw_tick = 0

        # Prefer a shared log file, then fallback to a per-user path if needed.
        # Logging is opt-in to reduce disk I/O.
        self.logfile = None
        enable_logging = bool(os.environ.get("DGC_LOG", ""))
        if enable_logging:
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

        # ACPI/root capability detection runs before building UI so unsupported
        # controls can be hidden on first render.
        self.init_acpi_call()
        self.setMinimumWidth(760)
        self.setMinimumHeight(560)
        self.setWindowTitle("Dell G Series Controller")
        # Read last choices from QSettings
        self.settings = QSettings('Dell-G15', 'Controller')
        self.theme_name = self.settings.value("Theme", "Blue")
        self._apply_theme()
        # Polling controls (fixed interval, toggleable)
        self.sensors_auto_refresh = self.settings.value("Sensors Auto Refresh", "True") == "True"
        # fixed interval (0.5s)
        self.sensors_interval = 0.5
        # Create grid layout
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        grid.setContentsMargins(20, 20, 20, 20)

        self.timer = None
        self.is_resizing = False
        self.sparkline_resize_timer = QTimer(self)
        self.sparkline_resize_timer.setSingleShot(True)
        self.sparkline_resize_timer.setInterval(250)
        self.sparkline_resize_timer.timeout.connect(self._update_sparklines)
        self.top_tabs = QTabWidget()
        self.top_tabs.addTab(self._create_first_exclusive_group(), "Keyboard Led")
        if (self.is_root and self.is_supported_5530):
            self.top_tabs.addTab(self._create_second_exclusive_group(), "Power and Fans")
        else:
            power_tab = self._create_power_unavailable_group()
            power_index = self.top_tabs.addTab(power_tab, "Power and Fans")
            self.top_tabs.setTabEnabled(power_index, False)

        grid.addWidget(self.top_tabs, 0, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        if (self.is_root and self.is_supported_5530):
            self.timer = QTimer(self)    # timer to update fan rpm values
            self.timer.setInterval(int(self.sensors_interval * 1000))
            self.timer.timeout.connect(self.get_rpm_and_temp)
            if self.sensors_auto_refresh:
                self.timer.start()

            # When ACPI is available we show two bottom panels: Diagnostics and Sensors
            self.diagnostics_group = self._create_diagnostics_group()
            grid.addWidget(self.diagnostics_group, 1, 0)
            self.sensors_group = self._create_sensors_group()
            grid.addWidget(self.sensors_group, 1, 1)
        else:
            grid.setColumnStretch(0, 1)
            # Only show diagnostics when ACPI/root is unavailable
            self.diagnostics_group = self._create_diagnostics_group()
            grid.addWidget(self.diagnostics_group, 1, 0)
        self.setLayout(grid)
        self._refresh_led_diagnostics()
        self._refresh_diagnostics()

    def _create_power_unavailable_group(self):
        group = QWidget()
        layout = QGridLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        message = QLabel("Power and fan controls require root access on a supported Dell G15 5530 model.")
        message.setWordWrap(True)
        layout.addWidget(message, 0, 0)
        return group

    def _refresh_led_diagnostics(self):
        try:
            version = self.led_service.get_version()
            self.led_version = f"{version[0]}.{version[1]}.{version[2]}"
        except Exception:
            self.led_version = "Unavailable"

    def _theme_color(self):
        theme_map = {
            "Red": "#ff4b4b",
            "Green": "#4bb664",
            "Purple": "#6200ff",
            "Pink": "#fc3c92",
            "Blue": "#00aaff",
            "Yellow": "#ffd24d",
            "Orange": "#ff6600",
        }
        return theme_map.get(self.theme_name, "#00aaff")

    def _set_theme(self, *_):
        if hasattr(self, "theme_choice"):
            self.theme_name = self.theme_choice.currentText()
        self.settings.setValue("Theme", self.theme_name)
        self._apply_theme()

    def _apply_theme(self):
        accent = self._theme_color()
        self.setStyleSheet("""
            QWidget {{
                background: #000000;
                color: #f2f2f2;
                font-size: 12px;
            }}
            QGroupBox {{
                border: 1px solid #f2f2f2;
                border-radius: 12px;
                margin-top: 14px;
                padding: 16px 12px 12px 12px;
                font-weight: 700;
                background-color: #000000;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #ffffff;
            }}
            QComboBox, QPushButton {{
                min-height: 30px;
                border-radius: 8px;
                border: 1px solid #ffffff;
                background-color: #050505;
                padding: 4px 10px;
            }}
            QComboBox:hover, QPushButton:hover {{
                border-color: {accent};
                background-color: #0f0f0f;
            }}
            QPushButton {{
                background-color: #111111;
                border-color: {accent};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #1b1b1b;
            }}
            QSlider::groove:horizontal {{
                height: 8px;
                border-radius: 4px;
                background: #1a1a1a;
            }}
            QSlider::sub-page:horizontal {{
                border-radius: 4px;
                background: {accent};
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
                background: #ffffff;
                border: 1px solid #000000;
            }}
            QLabel#previewLabel {{
                border: 1px solid #ffffff;
                border-radius: 8px;
                min-height: 30px;
                font-weight: 600;
                color: #000000;
                padding: 4px 8px;
            }}
            QLabel#colorCircle {{
                border: 2px solid #ffffff;
                border-radius: 32px;
                min-width: 64px;
                max-width: 64px;
                min-height: 64px;
                max-height: 64px;
                background: #ffffff;
            }}
        """.format(accent=accent))

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
            "set_power_mode" : ["0x15", "0x01"],    # To be used with a parameter
            "toggle_G_mode" : ["0x25", "0x01"],
            "get_G_mode" : ["0x25", "0x02"],
            "set_fan1_boost" : ["0x15", "0x02", "0x32"],            # To be used with a parameter
            "get_fan1_boost" : ["0x14", "0x0c", "0x32"],
            "get_fan1_rpm" : ["0x14", "0x05", "0x32"],
            "get_cpu_temp" : ["0x14", "0x04", "0x01"],
            "set_fan2_boost" : ["0x15", "0x02", "0x33"],            # To be used with a parameter
            "get_fan2_boost" : ["0x14", "0x0c", "0x33"],
            "get_fan2_rpm" : ["0x14", "0x05", "0x33"],
            "get_gpu_temp" : ["0x14", "0x04", "0x06"],
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

        # Startup logging kept minimal; errors only below.
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
        # Check if root or not
        whoami = startup_shell_exec("whoami")
        self.is_root = bool(whoami and len(whoami) > 1 and whoami[1].find("root") != -1)
        if not self.is_root:
            self._log_error("Root access denied")
            self.root_status = "Denied"
            self.acpi_status = "Unavailable"
            self.startup_status = "Root access denied"
            self._refresh_diagnostics()
            QMessageBox.warning(self, "Warning", "No root access. Power related functions will not work, and will not be displayed.")
            return

        # Root confirmed; keep stdout quiet unless actions/errors occur.
        self.root_status = "OK"
        self.acpi_status = "Ready"
        self.startup_status = "Root shell ready"
        self.acpi_service = AcpiService(self.shell, self.acpi_cmd, self.acpi_call_dict, verbose=False)

        self._check_laptop_model()

        if self.is_supported_5530:
            print("Laptop model is supported (Dell G15 5530).")
            self.startup_status = "Root OK; model supported"
        else:
            self.startup_status = "Root OK; model not supported"
            QMessageBox.warning(self, "Unsupported laptop", "This build is optimized for Dell G15 5530 only. Power and fan controls will stay hidden.")
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

    def _log_action(self, message):
        print(f"Action: {message}")

    def _log_error(self, message):
        print(f"Error: {message}")

    def _get_close_behavior(self):
        close_behavior = self.settings.value("Close Behavior", CLOSE_EXIT)
        return close_behavior if close_behavior in (CLOSE_EXIT, CLOSE_TRAY) else CLOSE_EXIT

    def _set_close_behavior(self, *_):
        self.settings.setValue("Close Behavior", self.close_behavior_choice.currentText())

    # Helper Functions
    # Execute given command in elevated shell
    def acpi_call(self, cmd, arg1="0x00", arg2="0x00"):
        # Track last response for diagnostics panel visibility.
        result = self.acpi_service.call(cmd, arg1, arg2)
        self.last_acpi_response = f"{cmd}: {result}"
        return result

    def shell_exec(self, cmd: str):
        print("Bash: Executing {}".format(cmd))
        self.shell.sendline(cmd)
        self.shell.expect("[#$] ")
        result = self.shell.before
        result = result.split('\n')
        for line in result[1:]:  # First line is the command that was sent
            print(line)
        return result

    def parse_shell_exec(self, line: str):
        return line[line.find('\r')+1:line.find('\x00')]  # Read between carriage return and end of the line

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
