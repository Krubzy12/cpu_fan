```markdown
# CPU Monitor & Fan Controller (Linux)

Ta aplikacja monitoruje parametry procesora i pozwala sterować wentylatorami przez kanały PWM (jeżeli system/płyta główna je udostępnia w /sys/class/hwmon).

Funkcje:
- wykresy czasu rzeczywistego: temperatura, taktowanie, użycie CPU, moc (jeśli dostępna),
- zapisywanie/wczytywanie profili (temperatura -> PWM),
- automatyczne stosowanie profilu do wszystkich dostępnych kanałów PWM,
- prosty edytor krzywej.

Wymagania:
- Linux (kernel exposes hwmon/pwm i/lub intel_rapl dla mocy)
- Python 3.8+
- sudo/root aby zapisywać wartości PWM.

Instalacja:
1. Zainstaluj wymagane pakiety systemowe:
   - lm-sensors (sudo apt install lm-sensors) i uruchom `sudo sensors-detect` jeśli chcesz mieć dokładniejsze odczyty hwmon.
2. Zainstaluj zależności Pythona:
   pip install -r requirements.txt

Uruchamianie:
- Monitorowanie bez zapisu PWM (dowolny użytkownik):
  python3 main.py
- Aby zmieniać PWM (wymaga uprawnień root):
  sudo python3 main.py

Profile:
- Profile zapisywane są w ~/.config/cpu-fan-controller/profiles/ jako pliki JSON.
- Możesz tworzyć profile przez GUI, zapisać i wczytać/dotować je.

Uruchomienie jako usługa (przykład):
1. Zapisz plik systemd cpu-fan-controller.service do /etc/systemd/system/
2. sudo systemctl daemon-reload
3. sudo systemctl enable --now cpu-fan-controller.service

Uwaga bezpieczeństwa:
- Zmienianie PWM wpływa na chłodzenie systemu — stosuj ostrożnie.
- Niektóre sterowniki sprzętowe mogą wymagać specyficznych ustawień (np. pwm_enable wartości inne niż 1).
```