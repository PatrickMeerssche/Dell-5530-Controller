from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from core.constants import CLOSE_BEHAVIORS


class PowerPanelMixin:
    # Power and fan controls.

    def _create_second_exclusive_group(self):
        # Power/fan controls require root and a supported model.
        groupBox = QGroupBox("")
        vbox = QVBoxLayout()
        vbox.setSpacing(10)

        widget = QWidget()
        hbox = QHBoxLayout(widget)

        # Power mode choice and Apply button
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

        theme_widget = QWidget()
        theme_hbox = QHBoxLayout(theme_widget)
        theme_hbox.setContentsMargins(0, 0, 0, 0)
        theme_hbox.setSpacing(8)
        theme_hbox.addWidget(QLabel("Color theme"))
        self.theme_choice = QComboBox()
        self.theme_choice.addItems([
            "Red",
            "Green",
            "Purple",
            "Pink",
            "Blue",
            "Yellow",
            "Orange",
        ])
        saved_theme = self.settings.value("Theme", "Blue")
        self.theme_choice.setCurrentText(saved_theme)
        theme_hbox.addWidget(self.theme_choice)

        # Fan 1 RPM
        self.fan1_label = QLabel("CPU Fan Boost")
        self.widget_fan1 = QWidget()
        hbox_fan1 = QHBoxLayout(self.widget_fan1)
        hbox_fan1.setContentsMargins(0, 0, 0, 0)
        hbox_fan1.setSpacing(8)
        self.fan1_boost = QSlider(orientation=Qt.Orientation.Horizontal)
        self.fan1_boost.setMinimum(0x00)
        self.fan1_boost.setMaximum(0xff)
        self.fan1_boost.setMinimumSize(100, 0)
        self.fan1_boost.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fan1_boost.setTickInterval(25.5)   # 10 steps
        self.fan1_boost.setValue(int(self.settings.value("Fan1 Boost", 0x00)))
        self.fan1_current = QLabel("0 RPM")
        hbox_fan1.addWidget(self.fan1_boost)
        hbox_fan1.addWidget(self.fan1_current)

        # Fan 2 RPM
        self.fan2_label = QLabel("GPU Fan Boost")
        self.widget_fan2 = QWidget()
        hbox_fan2 = QHBoxLayout(self.widget_fan2)
        hbox_fan2.setContentsMargins(0, 0, 0, 0)
        hbox_fan2.setSpacing(8)
        self.fan2_boost = QSlider(orientation=Qt.Orientation.Horizontal)
        self.fan2_boost.setMinimum(0x00)
        self.fan2_boost.setMaximum(0xff)
        self.fan2_boost.setMinimumSize(100, 0)
        self.fan2_boost.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.fan2_boost.setTickInterval(25.5)   # 10 steps
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

        # Add widgets to layout
        vbox.addWidget(self.combobox_mode_power)
        vbox.addWidget(self.fan1_label)
        vbox.addWidget(self.widget_fan1)
        vbox.addWidget(self.fan2_label)
        vbox.addWidget(self.widget_fan2)
        vbox.addWidget(self.live_fan_checkbox)
        vbox.addWidget(close_behavior_widget)
        vbox.addWidget(theme_widget)
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
        self.theme_choice.currentTextChanged.connect(self._set_theme)

        self._update_fan_boost_labels()
        self._refresh_fan_controls_visibility()

        # Return
        groupBox.setLayout(vbox)
        return groupBox

    def combobox_power(self):
        # Power-mode changes reset manual fan sliders and then confirm via ACPI.
        self.fan1_boost.setValue(0)
        self.fan2_boost.setValue(0)
        self.settings.setValue("Power", self.combobox_mode_power.currentText())
        choice = self.settings.value("Power", "USTT_Balanced")
        message = ""
        if hasattr(self, "_log_action"):
            self._log_action(f"Power mode selected: {choice}")

        # Set power mode
        mode = self.power_modes_dict[choice]
        self.acpi_call("set_power_mode", mode)
        # Get current power mode to confirm
        result = self.acpi_call("get_power_mode")
        if (result == mode):   # Expected result
            message = "Power mode set to {}.\n".format(choice)
        else:
            message = "Error! Command returned: {}, but expecting {}.\n".format(str(result), str(mode))
        # Get G Mode
        result = self.acpi_call("get_G_mode")
        if (choice == "G Mode") != (result == "0x1"):  # Toggle G Mode if needed.
            # Toggle G mode
            result_toggle = self.acpi_call("toggle_G_mode")
            if (("0x1" if choice == "G Mode" else "0x0") != result_toggle):
                message = message + "Expected to read G Mode = {} but read {}!\n".format(
                    choice == "G Mode", result_toggle
                )

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
        # Fan1 has id 0x32
        # Get current fan boost
        fan1_last_boost = self.acpi_call("get_fan1_boost")
        # Set new fan boost
        new_val = self.fan1_boost.value()
        self.acpi_call("set_fan1_boost", "0x{:2X}".format(new_val))
        # Get current fan boost
        fan1_new_boost = self.acpi_call("get_fan1_boost")
        self.info_label.setText(
            "Fan1 Boost: {:.0f}% to {:.0f}%.".format(
                int(fan1_last_boost, 0) / 0xff * 100,
                int(fan1_new_boost, 0) / 0xff * 100,
            )
        )
        if hasattr(self, "_log_action"):
            self._log_action(f"CPU fan boost set: {int(fan1_new_boost, 0) / 0xff * 100:.0f}%")
        self._refresh_diagnostics()

    def slider_fan2(self):
        if self.live_fan_checkbox.isChecked():
            return
        self._apply_fan2_boost()

    def _apply_fan2_boost(self):
        # Fan2 has id 0x33
        # Get current fan boost
        fan2_last_boost = self.acpi_call("get_fan2_boost")
        # Set new fan boost
        new_val = self.fan2_boost.value()
        self.acpi_call("set_fan2_boost", "0x{:2X}".format(new_val))
        # Get current fan boost
        fan2_new_boost = self.acpi_call("get_fan2_boost")
        self.info_label.setText(
            "Fan2 Boost: {:.0f}% to {:.0f}%.".format(
                int(fan2_last_boost, 0) / 0xff * 100,
                int(fan2_new_boost, 0) / 0xff * 100,
            )
        )
        if hasattr(self, "_log_action"):
            self._log_action(f"GPU fan boost set: {int(fan2_new_boost, 0) / 0xff * 100:.0f}%")
        self._refresh_diagnostics()
