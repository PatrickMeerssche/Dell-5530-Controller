from PySide6.QtWidgets import QGroupBox, QLabel, QVBoxLayout


class DiagnosticsPanelMixin:
    # Diagnostics panel.

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
