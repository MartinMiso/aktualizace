import time
import machine
import network
import urequests
import ahtx0
import cmath
import math
import update
from hx711 import HX711
from bmp280 import BMP280
from machine import I2S, Pin, I2C, ADC

# WiFi připojení
SSID = "Podhura 2"
PASSWORD = "truDy659"

# ThingSpeak API informace
THINGSPEAK_API_KEY = "OW890QF6K2CTV5P6"
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# URL k raw souboru na GitHubu
RAW_GITHUB_URL = "https://raw.githubusercontent.com/MartinMiso/aktualizace/refs/heads/main/main.py"

# Kalibrační faktor váhy
CALIBRATION_FACTOR = 27500

# Vzorkovací frekvence a počet vzorků pro FFT
FS = 16000  
N = 256  

# Inicializace I2C a senzorů
i2c = I2C(0, scl=Pin(22), sda=Pin(21))  
sensor = ahtx0.AHT20(i2c)
bmp = BMP280(i2c, address=0x77)

# Inicializace váhového senzoru HX711
hx = HX711(d_out=4, pd_sck=5)
hx.set_scale(CALIBRATION_FACTOR)
hx.tare()

# Inicializace ADC pro zvukový senzor
adc = ADC(Pin(32))
adc.atten(ADC.ATTN_11DB)

# Inicializace I2S mikrofonu INMP441
i2s = I2S(0, 
          sck=Pin(27), ws=Pin(25), sd=Pin(26),
          mode=I2S.RX, bits=16, format=I2S.MONO, rate=FS, ibuf=2048)

# Připojení k WiFi
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while not wlan.isconnected():
        pass
    print("Připojeno k WiFi:", wlan.ifconfig())

# Kontrola síly WiFi signálu
def get_wifi_signal_strength():
    wlan = network.WLAN(network.STA_IF)
    return wlan.status('rssi') if wlan.isconnected() else None

# Měření teploty, vlhkosti a tlaku
def wheather_sensor_measure():
    return sensor.temperature - 1.5, sensor.relative_humidity, *bmp.read_temperature_pressure()

# Měření váhy
def read_weight():
    return (hx.read_average(10) - tare_value) / CALIBRATION_FACTOR

# Odebrání vzorků zvuku
def get_samples():
    samples = [adc.read() for _ in range(N)]
    mean_value = sum(samples) / N
    return [s - mean_value for s in samples] 

# FFT a měření dominantní frekvence
def measure_freq():
    spectrum = fft(get_samples())
    magnitudes = [abs(c) for c in spectrum[:N // 2]]
    peak_index = magnitudes.index(max(magnitudes))
    return round(((peak_index * FS / N) / 2.05), 1)

def fft(signal):
    N = len(signal)
    if N <= 1:
        return signal
    even = fft(signal[0::2])
    odd = fft(signal[1::2])
    T = [cmath.exp(-2j * math.pi * k / N) * odd[k] for k in range(N // 2)]
    return [even[k] + T[k] for k in range(N // 2)] + [even[k] - T[k] for k in range(N // 2)]

# Odeslání dat na ThingSpeak
def send_data(temperature_aht, humidity_aht, temperature_bmp, pressure_bmp, weight, rssi, frekvence):
    url = (f"{THINGSPEAK_URL}?api_key={THINGSPEAK_API_KEY}"
           f"&field1={temperature_aht}&field2={humidity_aht}&field3={temperature_bmp}"
           f"&field4={pressure_bmp}&field5={weight}&field6={rssi}&field8={frekvence}")
    try:
        response = urequests.get(url)
        print("Odpověď serveru:", response.text)
        response.close()
    except Exception as e:
        print("Chyba při odesílání dat:", e)

# Odeslání WhatsApp zprávy přes CallMeBot
def send_whatsapp(number, api_key):
    message = "TEST+VČELY:+asi+si+balíme+baťůžky+a+mizíme+z+úlu!!!"
    url = f"https://api.callmebot.com/whatsapp.php?phone={number}&text={message}&apikey={api_key}"
    try:
        response = urequests.get(url)
        print("Odpověď serveru:", response.text)
    except Exception as e:
        print("Chyba:", e)

# Hluboký spánek
def deep_sleep(seconds):
    print(f"Přecházím do hlubokého spánku na {seconds // 1000} sekund.")
    machine.deepsleep(seconds)

# Připojení k WiFi
connect_wifi()

# Inicializace aktualizace přes GitHub
updater = update.Update(RAW_GITHUB_URL)
updater.compare_and_update("main.py")

# Načtení první uložené váhy
def load_first_weight():
    try:
        with open("first_weight.txt", "r") as file:
            return float(file.read())
    except (OSError, ValueError):
        return None 

first_weight = load_first_weight()

if first_weight is None:
    tare_value = hx.read_average(10)
    with open("first_weight.txt", "w") as file:
        file.write(str(tare_value))
else:
    tare_value = first_weight

while True:
    try:
        # Měření senzorů
        temp_aht, hum_aht, temp_bmp, pres_bmp = wheather_sensor_measure()
        weight = read_weight()
        rssi = get_wifi_signal_strength()
        frekvence = measure_freq()

        # Upozornění na vysokou frekvenci
        if 95 < frekvence < 260:
            send_whatsapp("420733113537", "3142801")  
            send_whatsapp("420603498872", "4097369")  
            print("Asi se rojíme!")

        # Odeslání dat
        send_data(temp_aht, hum_aht, temp_bmp, pres_bmp, weight, rssi, frekvence)

    except Exception as e:
        print("Chyba:", e)

    # Hluboký spánek na 10 minut
    deep_sleep(600000)


"""
mazaní tara.txt

import os

FLAG_FILE = "first_run.flag"
TARGET_FILE = "data.txt"

# Získáme seznam souborů v aktuálním adresáři
files = os.listdir()

# Pokud flag soubor ještě neexistuje
if FLAG_FILE not in files:
    try:
        os.remove(TARGET_FILE)
        print("Soubor {} byl smazán při prvním spuštění.".format(TARGET_FILE))
    except OSError:
        print("Soubor {} nebyl nalezen.".format(TARGET_FILE))
    # Vytvoříme flag soubor
    with open(FLAG_FILE, "w") as f:
        f.write("první spuštění proběhlo")
else:
    print("Flag soubor existuje – soubor {} nebyl smazán.".format(TARGET_FILE))
"""
