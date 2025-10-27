# fancontrol.py (zaktualizowane)
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
        # try to read name file in hwmon dir
        name_file = os.path.join(self.dir, "name")
        if os.path.exists(name_file):
            try:
                with open(name_file) as f:
                    return f.read().strip()
            except:
                pass
        # fallback to dirname
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
    """
    Odszukuje kanały PWM w /sys/class/hwmon/hwmon* i pozwala:
     - listować kanały (z opisem),
     - ustawiać PWM na wybranych kanałach lub na wszystkich,
     - zastosować krzywą (interpolacja).
    """
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
        # given list of pwm_file paths, return PWMChannel objects
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
        """
        curve_points: list of (tempC, pwm 0-255)
        channel_paths: optional list of pwm_file paths to apply to; if None -> all channels
        """
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
                        pwm = p0 + (p1 - p0) * frac
                    break
        pwm = max(0, min(255, int(pwm)))
        if channel_paths:
            errs = self.set_pwm_on_list(channel_paths, pwm)
        else:
            errs = self.set_pwm_on_all(pwm)
        return {"pwm": pwm, "errors": errs}