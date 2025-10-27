#!/usr/bin/env bash
# make_package.sh
# Tworzy katalog projektu cpu-fan-controller z pełnymi plikami i pakuje go do cpu-fan-controller.tar.gz oraz cpu-fan-controller.zip
#
# Użycie:
#   chmod +x make_package.sh
#   ./make_package.sh
#
set -euo pipefail

OUTDIR="cpu-fan-controller"
ARCHIVE_TGZ="${OUTDIR}.tar.gz"
ARCHIVE_ZIP="${OUTDIR}.zip"

rm -rf "${OUTDIR}" "${ARCHIVE_TGZ}" "${ARCHIVE_ZIP}"
mkdir -p "${OUTDIR}/profiles"

# requirements.txt
cat > "${OUTDIR}/requirements.txt" <<'EOF'
PyQt6>=6.5
pyqtgraph>=0.13
psutil>=5.9
EOF

# main.py
cat > "${OUTDIR}/main.py" <<'EOF'
#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication
from gui import MainWindow

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
EOF
chmod +x "${OUTDIR}/main.py"

# sensors.py
cat > "${OUTDIR}/sensors.py" <<'EOF'
import os
import time
import psutil
from collections import deque

class SensorReader:
    """
    Odczytuje temperatury, taktowanie, wykorzystanie CPU, napięcia (jeżeli dostępne)
    oraz moc CPU (jeżeli dostępne przez intel_rapl energy_uj).
    Używamy psutil tam gdzie możliwe i czytamy /sys gdzie potrzeba.
    """
    def __init__(self, sample_history=300):
        self.history_len = sample_history
        self.temp_history = deque(maxlen=sample_history)
        self.freq_history = deque(maxlen=sample_history)
        self.util_history = deque(maxlen=sample_history)
        self.power_history = deque(maxlen=sample_history)
        self.voltage = None
        self.last_energy = None
        self.last_energy_time = None
        self.rapl_path = self._find_rapl_energy()
        # initial sample
        self.sample()

    def _find_rapl_energy(self):
        base = "/sys/class/powercap"
        if not os.path.isdir(base):
            return None
        for ent in os.listdir(base):
            path = os.path.join(base, ent)
            for root, dirs, files in os.walk(path):
                if "energy_uj" in files:
                    return os.path.join(root, "energy_uj")
        return None

    def _read_energy_uj(self):
        try:
            if self.rapl_path:
                with open(self.rapl_path, "r") as f:
                    return int(f.read().strip())
        except Exception:
            return None
        return None

    def _read_voltage_from_hwmon(self):
        hwmon = "/sys/class/hwmon"
        if not os.path.isdir(hwmon):
            return None
        for h in os.listdir(hwmon):
            p = os.path.join(hwmon, h)
            for fname in os.listdir(p):
                if fname.startswith("in") and fname.endswith("_input"):
                    label = fname.replace("_input", "_label")
                    try:
                        val = None
                        with open(os.path.join(p, fname)) as f:
                            val = f.read().strip()
                        if val is None:
                            continue
                        lab = None
                        if os.path.exists(os.path.join(p, label)):
                            with open(os.path.join(p, label)) as f:
                                lab = f.read().strip().lower()
                        if lab and ("v" in lab or "voltage" in lab or "vcore" in lab):
                            try:
                                v = float(val) / 1000.0
                                return v
                            except:
                                continue
        return None

    def get_temperatures(self):
        temps = psutil.sensors_temperatures()
        temp_val = None
        if temps:
            for key in ("coretemp", "package-0", "k10temp", "cpu_thermal"):
                if key in temps:
                    readings = temps[key]
                    vals = [r.current for r in readings if getattr(r, 'current', None) is not None]
                    if vals:
                        temp_val = max(vals)
                        break
            if temp_val is None:
                vals = []
                for k, arr in temps.items():
                    for r in arr:
                        if getattr(r, 'current', None) is not None:
                            vals.append(r.current)
                if vals:
                    temp_val = max(vals)
        return temp_val

    def get_frequency(self):
        try:
            f = psutil.cpu_freq()
            if f and f.current:
                return f.current  # MHz
        except Exception:
            pass
        try:
            p = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"
            if os.path.exists(p):
                with open(p) as f:
                    return float(f.read().strip()) / 1000.0
        except Exception:
            pass
        return None

    def get_utilization(self):
        try:
            return psutil.cpu_percent(interval=None)
        except Exception:
            return None

    def get_power(self):
        e = self._read_energy_uj()
        now = time.time()
        if e is None:
            return None
        if self.last_energy is None:
            self.last_energy = e
            self.last_energy_time = now
            return None
        dt = now - self.last_energy_time
        if dt <= 0:
            return None
        de = e - self.last_energy
        if de < 0:
            de += 2**32
        watts = (de / 1e6) / dt
        self.last_energy = e
        self.last_energy_time = now
        return watts

    def get_voltage(self):
        v = self._read_voltage_from_hwmon()
        return v

    def sample(self):
        t = self.get_temperatures()
        f = self.get_frequency()
        u = self.get_utilization()
        p = self.get_power()
        v = self.get_voltage()
        self.temp_history.append(t if t is not None else 0.0)
        self.freq_history.append(f if f is not None else 0.0)
        self.util_history.append(u if u is not None else 0.0)
        self.power_history.append(p if p is not None else 0.0)
        self.voltage = v
        return {
            "temp": t,
            "freq": f,
            "util": u,
            "power": p,
            "voltage": v
        }
EOF

# fancontrol.py (updated)
cat > "${OUTDIR}/fancontrol.py" <<'EOF'
import os
import glob
import re
import json

class PWMChannel:
    def __init__(self, pwm_path):
        self.pwm_file = pwm_path
        self.dir = os.path.dirname(pwm_path)
        # determine hwmon name if available
        self.hwmon = os.path.basename(self.dir)
        # friendly name
        self.name = self._resolve_name()
        # find enable and fan input files if present
        self.enable_file = None
        self.fan_input_file = None
        for f in os.listdir(self.dir):
            if f.startswith("pwm") and f.endswith("_enable"):
                self.enable_file = os.path.join(self.dir, f)
            if re.match(r"fan\d+_input", f):
                self.fan_input_file = os.path.join(self.dir, f)

    def _resolve_name(self):
        name_file = os.path.join(self.dir, "name")
        if os.path.exists(name_file):
            try:
                with open(name_file) as f:
                    return f.read().strip()
            except:
                pass
        return self.hwmon

    def set_manual(self):
        if self.enable_file and os.path.exists(self.enable_file):
            try:
                with open(self.enable_file, "w") as f:
                    f.write("1")
            except Exception as e:
                raise PermissionError(f"Cannot set manual mode for {self.pwm_file}: {e}")

    def set_pwm(self, value):
        if not (0 <= value <= 255):
            raise ValueError("PWM value must be 0-255")
        if not os.path.exists(self.pwm_file):
            raise FileNotFoundError(self.pwm_file)
        try:
            with open(self.pwm_file, "w") as f:
                f.write(str(int(value)))
        except Exception as e:
            raise PermissionError(f"Cannot write pwm {self.pwm_file}: {e}")

    def read_rpm(self):
        if self.fan_input_file and os.path.exists(self.fan_input_file):
            try:
                with open(self.fan_input_file) as f:
                    return int(f.read().strip())
            except:
                return None
        return None

class FanController:
    def __init__(self):
        self.channels = self._discover_pwm_channels()

    def _discover_pwm_channels(self):
        hwmons = glob.glob("/sys/class/hwmon/hwmon*")
        channels = []
        for h in hwmons:
            for f in os.listdir(h):
                if re.match(r"pwm\d+$", f):
                    pwm_path = os.path.join(h, f)
                    try:
                        channels.append(PWMChannel(pwm_path))
                    except Exception:
                        continue
        return channels

    def list_channels(self):
        out = []
        for c in self.channels:
            out.append({
                "name": c.name,
                "hwmon": c.hwmon,
                "pwm_file": c.pwm_file,
                "enable_file": c.enable_file,
                "fan_input": c.fan_input_file
            })
        return out

    def _find_channels_by_paths(self, paths):
        out = []
        pathset = set(paths or [])
        for c in self.channels:
            if c.pwm_file in pathset:
                out.append(c)
        return out

    def set_pwm_on_list(self, paths, value):
        errs = []
        targets = self._find_channels_by_paths(paths)
        if not targets:
            errs.append("No matching PWM channels found for given paths")
        for c in targets:
            try:
                c.set_manual()
                c.set_pwm(value)
            except Exception as e:
                errs.append(str(e))
        return errs

    def set_pwm_on_all(self, value):
        errs = []
        for c in self.channels:
            try:
                c.set_manual()
                c.set_pwm(value)
            except Exception as e:
                errs.append(str(e))
        return errs

    def apply_curve(self, temp_c, curve_points, channel_paths=None):
        if not curve_points:
            return None
        pts = sorted(curve_points, key=lambda x: x[0])
        if temp_c <= pts[0][0]:
            pwm = pts[0][1]
        elif temp_c >= pts[-1][0]:
            pwm = pts[-1][1]
        else:
            pwm = pts[-1][1]
            for i in range(len(pts)-1):
                t0, p0 = pts[i]
                t1, p1 = pts[i+1]
                if t0 <= temp_c <= t1:
                    if t1 == t0:
                        pwm = p1
                    else:
                        frac = (temp_c - t0) / (t1 - t0)
                        pwm = p0 + (p1 - p0
