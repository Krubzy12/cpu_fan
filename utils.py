# utils.py (zaktualizowane: wspiera profile użytkownika i profile systemowe)
import os
import json
import getpass

def config_dir(user_home=None):
    if user_home is None:
        home = os.path.expanduser("~")
    else:
        home = user_home
    d = os.path.join(home, ".config", "cpu-fan-controller")
    os.makedirs(os.path.join(d, "profiles"), exist_ok=True)
    return d

def profiles_dir(user_home=None):
    return os.path.join(config_dir(user_home), "profiles")

def system_profiles_dir():
    d = "/etc/cpu-fan-controller/profiles"
    os.makedirs(d, exist_ok=True)
    return d

def save_profile(name, profile_dict, system=False):
    if system:
        if os.geteuid() != 0:
            raise PermissionError("Saving system profile requires root")
        pdir = system_profiles_dir()
    else:
        pdir = profiles_dir()
    path = os.path.join(pdir, f"{name}.json")
    with open(path, "w") as f:
        json.dump(profile_dict, f, indent=2)

def load_profile(name):
    # try user profile then system profile
    user_path = os.path.join(profiles_dir(), f"{name}.json")
    if os.path.exists(user_path):
        with open(user_path) as f:
            return json.load(f)
    sys_path = os.path.join(system_profiles_dir(), f"{name}.json")
    if os.path.exists(sys_path):
        with open(sys_path) as f:
            return json.load(f)
    raise FileNotFoundError(f"Profile {name} not found in user or system profiles")

def list_profiles():
    out = []
    # user profiles
    pdir = profiles_dir()
    if os.path.exists(pdir):
        for fn in os.listdir(pdir):
            if fn.endswith(".json"):
                out.append(fn[:-5])
    # system profiles (prefix with sys/ to indicate origin)
    sdir = system_profiles_dir()
    if os.path.exists(sdir):
        for fn in os.listdir(sdir):
            if fn.endswith(".json"):
                name = fn[:-5]
                if name not in out:
                    out.append(name)
    return out