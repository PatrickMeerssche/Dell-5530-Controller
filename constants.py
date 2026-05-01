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
