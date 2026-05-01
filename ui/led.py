from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget, QColorDialog, QGroupBox

from core.constants import (
    MODE_STATIC,
    MODE_MORPH,
    MODE_OFF,
    LED_MODES,
    BRIGHTNESS_HIGH,
    BRIGHTNESS_LEVELS,
    BRIGHTNESS_DIM_MAP,
)


class LedPanelMixin:
    # LED control UI and actions.

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
        self.static_circle.setStyleSheet(
            f"background-color: {static_hex}; border: 2px solid #ffffff; border-radius: 32px;"
        )

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
            self.brightness_choice.setCurrentText(
                saved_brightness if saved_brightness in BRIGHTNESS_LEVELS else BRIGHTNESS_HIGH
            )

            self.duration_label = QLabel("Duration")
            self.duration = QSlider(orientation=Qt.Orientation.Horizontal)
            self.duration.setMinimum(0x4)
            self.duration.setMaximum(0xfff)
            self.duration.setMinimumSize(100, 0)
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
        # Return
        groupBox.setLayout(vbox)
        return groupBox

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
            else:   # Off
                self.remove_animation()
            self.info_led_label.setText("Applied successfully.")
            self.last_led_status = "Apply successful"
            self._refresh_diagnostics()
            self._refresh_apply_button_state()
        except Exception as err:
            self.info_led_label.setText(f"Apply failed: {err.__class__.__name__}")
            self.last_led_status = f"Apply failed: {err.__class__.__name__}"
            self._refresh_diagnostics()
            QMessageBox.warning(self, "Error", f"Cannot apply LED settings:\n\n{err.__class__.__name__}: {err}")
            raise err

    # Apply given colors to keyboard.
    def apply_static(self):
        # Program effect first, then dim, so brightness remains persistent.
        self.led_service.set_static(self.static_red, self.static_green, self.static_blue)
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
        self.led_service.set_morph(red_morph, green_morph, blue_morph, self.duration.value())
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
