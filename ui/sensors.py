from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QGroupBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class SensorsPanelMixin:
    # Sensors panel and polling.

    def _draw_sparkline(self, values, width=160, height=28, line_color=QColor('#66ccff')):
        # Allow dynamic sizing when width/height are None or zero
        if not width:
            width = 160
        if not height:
            height = 28
        pix = QPixmap(int(width), int(height))
        pix.fill(QColor('#000000'))
        if not values:
            return pix
        painter = QPainter(pix)
        pen = QPen(line_color)
        pen.setWidth(2)
        painter.setPen(pen)
        # Scale values to widget height
        mn = min(values)
        mx = max(values)
        rng = mx - mn if mx != mn else 1
        pts = []
        step = width / max(1, (len(values) - 1))
        for i, v in enumerate(values):
            x = int(i * step)
            y = int((1 - (v - mn) / rng) * (height - 4)) + 2
            pts.append((x, y))
        # Draw polyline
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1])
        painter.end()
        return pix

    def _update_sparklines(self):
        try:
            # Compute sizes based on current widget geometry so sparklines resize
            def size_for(widget):
                w = widget.width() or 120
                h = widget.height() or 28
                return max(80, w), max(20, h)

            w, h = size_for(self.spark_cpu)
            self.spark_cpu.setPixmap(self._draw_sparkline(list(self.cpu_history), w, h))
            w, h = size_for(self.spark_gpu)
            self.spark_gpu.setPixmap(self._draw_sparkline(list(self.gpu_history), w, h))
            w, h = size_for(self.spark_fan1)
            self.spark_fan1.setPixmap(self._draw_sparkline(list(self.fan1_history), w, h, line_color=QColor('#ffcc66')))
            w, h = size_for(self.spark_fan2)
            self.spark_fan2.setPixmap(self._draw_sparkline(list(self.fan2_history), w, h, line_color=QColor('#ff66cc')))
            self.is_resizing = False
        except Exception:
            pass

    def _sensors_autorefresh_changed(self, enabled):
        self.sensors_auto_refresh = bool(enabled)
        self.settings.setValue("Sensors Auto Refresh", str(self.sensors_auto_refresh))
        if hasattr(self, 'timer') and self.timer is not None:
            if self.sensors_auto_refresh:
                # fixed 0.5s interval
                self.timer.setInterval(int(self.sensors_interval * 1000))
                self.timer.start()
            else:
                self.timer.stop()

    def showEvent(self, event):
        # Resume polling when window becomes visible
        try:
            if self.sensors_auto_refresh and hasattr(self, 'timer') and self.timer is not None:
                self.timer.setInterval(int(self.sensors_interval * 1000))
                self.timer.start()
        except Exception:
            pass
        return super().showEvent(event)

    def hideEvent(self, event):
        # Pause polling when window hidden to save resources
        try:
            if hasattr(self, 'timer') and self.timer is not None:
                self.timer.stop()
        except Exception:
            pass
        return super().hideEvent(event)

    def resizeEvent(self, event):
        # Keep sparklines in sync with the available width
        try:
            if hasattr(self, 'spark_cpu'):
                if hasattr(self, 'sparkline_resize_timer'):
                    self.is_resizing = True
                    self.sparkline_resize_timer.start()
                else:
                    self._update_sparklines()
        except Exception:
            pass
        return super().resizeEvent(event)

    def _create_sensors_group(self):
        # Small panel that shows CPU/GPU temps and fan RPMs.
        group = QGroupBox("Sensors")
        layout = QVBoxLayout()
        layout.setSpacing(6)

        # Current value labels
        self.sensor_cpu_label = QLabel("CPU Temp: N/A")
        self.sensor_gpu_label = QLabel("GPU Temp: N/A")
        self.sensor_fan1_label = QLabel("CPU Fan: N/A RPM")
        self.sensor_fan2_label = QLabel("GPU Fan: N/A RPM")

        # Sparklines (resize with window)
        self.spark_cpu = QLabel()
        self.spark_gpu = QLabel()
        self.spark_fan1 = QLabel()
        self.spark_fan2 = QLabel()
        for spark in (self.spark_cpu, self.spark_gpu, self.spark_fan1, self.spark_fan2):
            spark.setMinimumHeight(28)
            spark.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Auto-refresh controls
        controls_widget = QWidget()
        controls_hbox = QHBoxLayout(controls_widget)
        controls_hbox.setContentsMargins(0, 0, 0, 0)
        controls_hbox.setSpacing(8)
        self.sensors_autorefresh_checkbox = QCheckBox("Auto refresh (0.5s)")
        self.sensors_autorefresh_checkbox.setChecked(self.sensors_auto_refresh)
        controls_hbox.addWidget(self.sensors_autorefresh_checkbox)
        # Interval is fixed at 0.5s — no user control required
        controls_hbox.addStretch(1)

        # Layout items
        layout.addWidget(self.sensor_cpu_label)
        layout.addWidget(self.spark_cpu)
        layout.addWidget(self.sensor_gpu_label)
        layout.addWidget(self.spark_gpu)
        layout.addWidget(self.sensor_fan1_label)
        layout.addWidget(self.spark_fan1)
        layout.addWidget(self.sensor_fan2_label)
        layout.addWidget(self.spark_fan2)
        layout.addWidget(controls_widget)

        # Wire controls
        self.sensors_autorefresh_checkbox.toggled.connect(self._sensors_autorefresh_changed)
        # Apply current setting immediately
        try:
            self._sensors_autorefresh_changed(self.sensors_auto_refresh)
        except Exception:
            pass

        group.setLayout(layout)
        # Initialize empty sparklines
        self._update_sparklines()
        return group

    def get_rpm_and_temp(self):
        # Only poll when auto-refresh is enabled, window is visible, and sensors panel is visible.
        if not (self.sensors_auto_refresh and self.isVisible() and hasattr(self, 'sensors_group') and self.sensors_group.isVisible()):
            return
        # Proceed with polling
        # Get current rpm and temp from ACPI and update both the Power/Fans
        # panel and the new Sensors panel.
        try:
            fan1_rpm = self.acpi_call("get_fan1_rpm")
            cpu_temp = self.acpi_call("get_cpu_temp")
            fan2_rpm = self.acpi_call("get_fan2_rpm")
            gpu_temp = self.acpi_call("get_gpu_temp")
        except Exception as err:
            # ACPI call failed; record and skip this cycle
            self.last_acpi_response = f"error: {err.__class__.__name__}"
            self._refresh_diagnostics()
            return

        # Parse and update existing Power and Fans RPM labels
        try:
            cpu_val = int(cpu_temp, 0)
            gpu_val = int(gpu_temp, 0)
            fan1_val = int(fan1_rpm, 0)
            fan2_val = int(fan2_rpm, 0)
        except Exception:
            # Non-numeric response; ignore this cycle
            return

        try:
            self.fan1_current.setText("{} RPM, {} °C".format(fan1_val, cpu_val))
            self.fan2_current.setText("{} RPM, {} °C".format(fan2_val, gpu_val))
        except Exception:
            pass

        current_values = (cpu_val, gpu_val, fan1_val, fan2_val)
        if current_values == self.last_sensor_values:
            # No change; skip history and redraw to reduce churn
            return
        self.last_sensor_values = current_values

        # Append history and update sparklines/labels
        self.cpu_history.append(cpu_val)
        self.gpu_history.append(gpu_val)
        self.fan1_history.append(fan1_val)
        self.fan2_history.append(fan2_val)

        try:
            self.sensor_cpu_label.setText(f"CPU Temp: {cpu_val} °C")
            self.sensor_gpu_label.setText(f"GPU Temp: {gpu_val} °C")
            self.sensor_fan1_label.setText(f"CPU Fan: {fan1_val} RPM")
            self.sensor_fan2_label.setText(f"GPU Fan: {fan2_val} RPM")
            # no last-update display (fixed-rate refresh)
            self.sparkline_redraw_tick += 1
            if not self.is_resizing and (self.sparkline_redraw_tick % 3 == 0):
                self._update_sparklines()
        except Exception:
            pass
