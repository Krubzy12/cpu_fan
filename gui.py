# gui.py (zaktualizowane: obsługa wyboru kanałów PWM, zapisywanie ich w profilach)
import os
import time
import json
from PyQt6.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QLabel,
                             QPushButton, QListWidget, QMessageBox, QHBoxLayout,
                             QTableWidget, QTableWidgetItem, QFileDialog, QListWidgetItem,
                             QCheckBox)
import pyqtgraph as pg

from sensors import SensorReader
from fancontrol import FanController
import utils

class PollThread(QThread):
    sample_signal = pyqtSignal(dict)
    def __init__(self, interval=1.0):
        super().__init__()
        self.interval = interval
        self._running = True
        self.reader = SensorReader()
    def run(self):
        while self._running:
            data = self.reader.sample()
            self.sample_signal.emit(data)
            time.sleep(self.interval)
    def stop(self):
        self._running = False

class ControlThread(QThread):
    applied_pwm = pyqtSignal(int)
    def __init__(self, controller, curve_points, channel_paths=None, mode='auto', interval=2.0):
        super().__init__()
        self.controller = controller
        self.curve = curve_points[:]
        self.channel_paths = channel_paths[:] if channel_paths else None
        self.interval = interval
        self.mode = mode
        self._running = True
        self.current_temp = 0.0
    def set_temp(self, t):
        self.current_temp = t
    def set_curve(self, pts):
        self.curve = pts[:]
    def set_channels(self, paths):
        self.channel_paths = paths[:] if paths else None
    def run(self):
        while self._running:
            if self.mode == 'auto' and self.curve:
                res = self.controller.apply_curve(self.current_temp, self.curve, self.channel_paths)
                if res and 'pwm' in res:
                    self.applied_pwm.emit(int(res['pwm']))
            time.sleep(self.interval)
    def stop(self):
        self._running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CPU Monitor & Fan Controller")
        self.resize(1100, 750)
        self.reader = SensorReader()
        self.controller = FanController()
        self.poll_thread = PollThread(interval=1.0)
        self.poll_thread.sample_signal.connect(self.on_sample)
        self.poll_thread.start()

        self._build_ui()

        # start control thread but in manual mode initially
        self.control_thread = ControlThread(self.controller, [], channel_paths=None, mode='manual', interval=2.0)
        self.control_thread.applied_pwm.connect(self.on_applied_pwm)
        self.control_thread.start()

        self.latest_temp = 0.0

    def closeEvent(self, event):
        try:
            self.poll_thread.stop()
            self.poll_thread.wait(500)
        except:
            pass
        try:
            self.control_thread.stop()
            self.control_thread.wait(500)
        except:
            pass
        event.accept()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout()
        central.setLayout(layout)

        # Left: plots and stats
        left = QVBoxLayout()
        layout.addLayout(left, 3)

        # Stats labels
        self.lbl_temp = QLabel("Temp: -- °C")
        self.lbl_freq = QLabel("Freq: -- MHz")
        self.lbl_util = QLabel("Util: -- %")
        self.lbl_power = QLabel("Power: -- W")
        self.lbl_volt = QLabel("Volt: -- V")
        lbl_layout = QHBoxLayout()
        for w in (self.lbl_temp, self.lbl_freq, self.lbl_util, self.lbl_power, self.lbl_volt):
            lbl_layout.addWidget(w)
        left.addLayout(lbl_layout)

        # Plots
        self.plot_widget = pg.GraphicsLayoutWidget()
        left.addWidget(self.plot_widget, 1)
        self.p1 = self.plot_widget.addPlot(title="Temperature (°C)")
        self.curve_temp = self.p1.plot(pen='r')
        self.plot_widget.nextRow()
        self.p2 = self.plot_widget.addPlot(title="Frequency (MHz)")
        self.curve_freq = self.p2.plot(pen='g')
        self.plot_widget.nextRow()
        self.p3 = self.plot_widget.addPlot(title="Utilization (%)")
        self.curve_util = self.p3.plot(pen='b')
        self.plot_widget.nextRow()
        self.p4 = self.plot_widget.addPlot(title="Power (W)")
        self.curve_power = self.p4.plot(pen='y')

        # Right: control panel
        right = QVBoxLayout()
        layout.addLayout(right, 2)

        # PWM channel list (with checkboxes)
        right.addWidget(QLabel("Detected PWM channels (zaznacz te, które chcesz kontrolować):"))
        self.ch_list = QListWidget()
        right.addWidget(self.ch_list)
        self._refresh_channels()

        btn_refresh = QPushButton("Refresh Channels")
        btn_refresh.clicked.connect(self._refresh_channels)
        right.addWidget(btn_refresh)

        # Curve editor (table)
        right.addWidget(QLabel("Fan curve (Temperature °C -> PWM 0-255)"))
        self.curve_table = QTableWidget(0, 2)
        self.curve_table.setHorizontalHeaderLabels(["Temp (°C)", "PWM (0-255)"])
        right.addWidget(self.curve_table)

        btn_row_add = QPushButton("Add point")
        btn_row_add.clicked.connect(self.add_point)
        btn_row_remove = QPushButton("Remove selected")
        btn_row_remove.clicked.connect(self.remove_point)
        row_btns = QHBoxLayout()
        row_btns.addWidget(btn_row_add)
        row_btns.addWidget(btn_row_remove)
        right.addLayout(row_btns)

        # Profile management
        right.addWidget(QLabel("Profiles"))
        prof_layout = QHBoxLayout()
        self.profile_list = QListWidget()
        self._refresh_profiles()
        prof_layout.addWidget(self.profile_list)
        prof_btns = QVBoxLayout()
        btn_save = QPushButton("Save profile (user)")
        btn_save.clicked.connect(self.save_profile)
        btn_save_sys = QPushButton("Save profile (system)")
        btn_save_sys.clicked.connect(lambda: self.save_profile(system=True))
        btn_load = QPushButton("Load profile")
        btn_load.clicked.connect(self.load_profile)
        btn_apply = QPushButton("Apply profile now")
        btn_apply.clicked.connect(self.apply_profile_now)
        btn_export = QPushButton("Export profile...")
        btn_export.clicked.connect(self.export_profile)
        prof_btns.addWidget(btn_save)
        prof_btns.addWidget(btn_save_sys)
        prof_btns.addWidget(btn_load)
        prof_btns.addWidget(btn_apply)
        prof_btns.addWidget(btn_export)
        prof_layout.addLayout(prof_btns)
        right.addLayout(prof_layout)

        # Auto control toggle
        self.btn_start_auto = QPushButton("Start Auto Control")
        self.btn_start_auto.setCheckable(True)
        self.btn_start_auto.clicked.connect(self.toggle_auto)
        right.addWidget(self.btn_start_auto)

        # Manual apply
        self.spin_manual = QTableWidgetItem
        from PyQt6.QtWidgets import QSpinBox
        self.spin_manual = QSpinBox()
        self.spin_manual.setRange(0, 255)
        btn_apply_manual = QPushButton("Set manual PWM to selected channels")
        btn_apply_manual.clicked.connect(self.apply_manual_pwm)
        right.addWidget(QLabel("Manual PWM:"))
        mw = QHBoxLayout()
        mw.addWidget(self.spin_manual)
        mw.addWidget(btn_apply_manual)
        right.addLayout(mw)

        # status
        self.lbl_status = QLabel("")
        right.addWidget(self.lbl_status)

        # timer to update plots
        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plots)
        self.plot_timer.start(1000)

    def _refresh_channels(self):
        self.ch_list.clear()
        chans = self.controller.list_channels()
        if not chans:
            item = QListWidgetItem("No pwm channels found in /sys/class/hwmon")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.ch_list.addItem(item)
        else:
            for c in chans:
                text = f"{c['name']} | {c['pwm_file']}"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, c['pwm_file'])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                self.ch_list.addItem(item)

    def _selected_channel_paths(self):
        paths = []
        for i in range(self.ch_list.count()):
            item = self.ch_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                pv = item.data(Qt.ItemDataRole.UserRole)
                if pv:
                    paths.append(pv)
        return paths

    def add_point(self):
        row = self.curve_table.rowCount()
        self.curve_table.insertRow(row)
        self.curve_table.setItem(row, 0, QTableWidgetItem("50"))
        self.curve_table.setItem(row, 1, QTableWidgetItem("128"))

    def remove_point(self):
        r = self.curve_table.currentRow()
        if r >= 0:
            self.curve_table.removeRow(r)

    def _read_curve_from_table(self):
        pts = []
        for r in range(self.curve_table.rowCount()):
            try:
                t = float(self.curve_table.item(r,0).text())
                p = int(self.curve_table.item(r,1).text())
                pts.append((t, p))
            except:
                continue
        pts.sort(key=lambda x:x[0])
        return pts

    def save_profile(self, system=False):
        # prompt for name
        name, _ = QFileDialog.getSaveFileName(self, "Save profile", utils.profiles_dir(), "JSON files (*.json)")
        if not name:
            return
        if not name.endswith(".json"):
            name = name + ".json"
        pts = self._read_curve_from_table()
        prof = {
            "name": os.path.basename(name).rsplit(".",1)[0],
            "points": pts,
            "channels": self._selected_channel_paths()
        }
        try:
            if system:
                # try save to system path via utils
                utils.save_profile(prof['name'], prof, system=True)
            else:
                with open(name, "w") as f:
                    json.dump(prof, f, indent=2)
            self._refresh_profiles()
            self.lbl_status.setText(f"Saved profile {name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save profile: {e}")

    def load_profile(self):
        sel = self.profile_list.currentItem()
        if not sel:
            QMessageBox.information(self, "Info", "Select a profile first")
            return
        name = sel.text()
        try:
            prof = utils.load_profile(name)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot load profile: {e}")
            return
        # populate table
        self.curve_table.setRowCount(0)
        for t,p in prof.get("points", []):
            r = self.curve_table.rowCount()
            self.curve_table.insertRow(r)
            self.curve_table.setItem(r, 0, QTableWidgetItem(str(t)))
            self.curve_table.setItem(r, 1, QTableWidgetItem(str(p)))
        # set channels
        paths = prof.get("channels", [])
        # uncheck all and check matching ones
        for i in range(self.ch_list.count()):
            item = self.ch_list.item(i)
            pv = item.data(Qt.ItemDataRole.UserRole)
            if pv and pv in paths:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
        self.lbl_status.setText(f"Loaded profile {name}")

    def apply_profile_now(self):
        pts = self._read_curve_from_table()
        if not pts:
            QMessageBox.information(self, "Info", "No points in curve")
            return
        paths = self._selected_channel_paths()
        res = self.controller.apply_curve(self.latest_temp, pts, channel_paths=paths)
        if isinstance(res, dict):
            self.lbl_status.setText(f"Applied profile -> PWM {res.get('pwm')} (errors: {res.get('errors')})")
        else:
            self.lbl_status.setText(f"Applied profile -> PWM {res}")

    def export_profile(self):
        sel = self.profile_list.currentItem()
        if not sel:
            QMessageBox.information(self, "Info", "Select a profile to export")
            return
        name = sel.text()
        try:
            prof = utils.load_profile(name)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Cannot load profile: {e}")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export profile", f"{name}.json", "JSON files (*.json)")
        if not path:
            return
        with open(path, "w") as f:
            json.dump(prof, f, indent=2)
        self.lbl_status.setText(f"Exported to {path}")

    def toggle_auto(self, checked):
        if checked:
            pts = self._read_curve_from_table()
            if not pts:
                QMessageBox.information(self, "Info", "Add some curve points first")
                self.btn_start_auto.setChecked(False)
                return
            paths = self._selected_channel_paths()
            self.control_thread.set_curve(pts)
            self.control_thread.set_channels(paths)
            self.control_thread.mode = 'auto'
            self.lbl_status.setText("Auto control started")
        else:
            self.control_thread.mode = 'manual'
            self.lbl_status.setText("Auto control stopped")

    def apply_manual_pwm(self):
        v = self.spin_manual.value()
        paths = self._selected_channel_paths()
        try:
            if paths:
                errs = self.controller.set_pwm_on_list(paths, v)
            else:
                errs = self.controller.set_pwm_on_all(v)
            if errs:
                self.lbl_status.setText("Some errors: " + "; ".join(errs))
            else:
                self.lbl_status.setText(f"Set manual PWM={v} on selected channels")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set PWM: {e}")

    def on_sample(self, data):
        t = data.get("temp")
        f = data.get("freq")
        u = data.get("util")
        p = data.get("power")
        v = data.get("voltage")
        if t is not None:
            self.lbl_temp.setText(f"Temp: {t:.1f} °C")
            self.latest_temp = t
            self.control_thread.set_temp(t)
        if f is not None:
            self.lbl_freq.setText(f"Freq: {f:.0f} MHz")
        if u is not None:
            self.lbl_util.setText(f"Util: {u:.1f} %")
        if p is not None:
            try:
                self.lbl_power.setText(f"Power: {p:.2f} W")
            except:
                self.lbl_power.setText("Power: -- W")
        if v is not None:
            self.lbl_volt.setText(f"Volt: {v:.3f} V")

    def update_plots(self):
        reader = self.poll_thread.reader
        try:
            temp_hist = list(reader.temp_history)
            freq_hist = list(reader.freq_history)
            util_hist = list(reader.util_history)
            power_hist = list(reader.power_history)
            x = list(range(-len(temp_hist)+1,1))
            if temp_hist:
                self.curve_temp.setData(x, temp_hist)
            if freq_hist:
                self.curve_freq.setData(x, freq_hist)
            if util_hist:
                self.curve_util.setData(x, util_hist)
            if power_hist:
                self.curve_power.setData(x, power_hist)
        except Exception:
            pass

    def on_applied_pwm(self, pwm):
        self.lbl_status.setText(f"Auto applied PWM={pwm}")