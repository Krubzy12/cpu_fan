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
                    except Exception:
                        # ignore errors reading this hwmon entry and continue to next
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