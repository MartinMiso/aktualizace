import os
import time
import math
import ahtx0
import utime
import cmath
import update
import network
import machine
import urequests
from hx711 import HX711
from machine import Timer
from bmp280 import BMP280
from machine import I2S, Pin, I2C, ADC


# WiFi připojení
SSID = "Podhura 2"
PASSWORD = "truDy659"

# Nastavení ADC
adc = machine.ADC(machine.Pin(32))
adc.atten(machine.ADC.ATTN_11DB)

FS = 16000  # Vzorkovací frekvence
N = 256  # Počet vzorků (vyšší N = přesnější, ale pomalejší)


# Nastavení I2C sběrnice
i2c = I2C(0, scl=Pin(22), sda=Pin(21))  # BMP280 + AHT20 senzor
# Inicializace AHT20
sensor = ahtx0.AHT20(i2c)
# Inicializace BMP280
bmp = BMP280(i2c, address=0x77)
print(i2c.scan())

# Definice pinů pro HX711
DT = 4   # Data pin (DT)
SCK = 5  # Clock pin (SCK)
# Inicializace HX711
hx = HX711(d_out=DT, pd_sck=SCK)
hx.tare()
#tare_value = hx.offset

# wifi připojení
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)
    while not wlan.isconnected():
        pass
    print("Připojeno k WiFi:", wlan.ifconfig())

# síla wifi signálu
def get_wifi_signal_strength():
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        rssi = wlan.status('rssi')  # Vrátí sílu signálu v dBm
        print(f"Síla signálu WiFi: {rssi} dBm")
        return rssi
    else:
        print("ESP není připojeno k WiFi.")
        return None

# URL k raw souboru na GitHubu
RAW_GITHUB_URL = "https://raw.githubusercontent.com/MartinMiso/aktualizace/refs/heads/main/main.py"

# Interval pro aktualizaci (1 týden = 7 dní * 24 hodin * 60 minut * 60 sekund)
ONE_WEEK = 1 * 1 * 1 * 1

# ThingSpeak API informace
THINGSPEAK_API_KEY = "OW890QF6K2CTV5P6"  # Nahraďte vaším Write API Key
THINGSPEAK_URL = "https://api.thingspeak.com/update"


# Kalibrační faktor
CALIBRATION_FACTOR = 27500
hx.set_scale(CALIBRATION_FACTOR)
# první měření pro uložení při ztrátě dat pro probuzení z deep sleep
#first_value = hx.read_average(10)
#first_weight = (value - hx.offset) / CALIBRATION_FACTOR


# Funkce pro uložení první váhy - prázdného úlu do souboru
def save_first_weight(first_weight):
    with open("first_weight.txt", "w") as file:
        file.write(str(first_weight))
    print(f"Tara {first_weight} uložena do souboru.")


# Funkce pro načtení tary ze souboru
def load_first_weight():
    try:
        with open("first_weight.txt", "r") as file:
            first_weight = float(file.read())
        print(f"Načtena tara ze souboru: {first_weight}")
        return first_weight
    except (OSError, ValueError):
        print("Tara nenalezena nebo poškozena. Nastavuje se výchozí.")
        return None # Výchozí hodnota tary


# Funkce pro odeslání dat na ThingSpeak
def send_data(temperature_aht, humidity_aht, temperature_bmp, pressure_bmp, weight, rssi, prum_frekvence):
    # Vytvoření URL s parametry
    url = (f"{THINGSPEAK_URL}?api_key={THINGSPEAK_API_KEY}"
           f"&field1={temperature_aht}"
           f"&field2={humidity_aht}"
           f"&field3={temperature_bmp}"
           f"&field4={pressure_bmp}"
           f"&field5={weight}"
           f"&field6={rssi}"
           f"&field7={prum_frekvence}"
           )
    
    try:
        # Odeslání požadavku
        response = urequests.get(url)
        print("Odpověď serveru:", response.text)
        response.close()
    except Exception as e:
        print("Chyba při odesílání dat na ThingSpeak:", e)


def wheather_sensor_measure():
    # Čtení dat z AHT20
    temperature_aht = sensor.temperature
    humidity_aht = sensor.relative_humidity
    print("AHT senzor:")
    print(f"Teplota: {temperature_aht:.2f} °C, Vlhkost: {humidity_aht:.2f} %")

    # Čtení dat z BMP280
    temperature_bmp, pressure_bmp = bmp.read_temperature_pressure()
    print("BMP senzor:")
    print(f"Teplota: {temperature_bmp:.2f} °C, Tlak: {pressure_bmp:.2f} hPa")
    return temperature_aht, humidity_aht, temperature_bmp, pressure_bmp


def read_weight():
    # Získání průměrné hodnoty (20 měření)
    value = hx.read_average(10)
    weight = (value - tare_value) / CALIBRATION_FACTOR
    #weight = (value - hx.offset) / CALIBRATION_FACTOR
    print(f"Váha: {weight} kg")
    return weight


# Měření frekvence
def get_samples():
    """Odebere N vzorků z ADC a odstraní DC složku."""
    samples = []
    for _ in range(N):
        samples.append(adc.read())
        utime.sleep_us(int(1e6 / FS))  # Odpovídá FS vzorků za sekundu
    
    mean_value = sum(samples) / len(samples)
    samples = [s - mean_value for s in samples]  # Odečtení DC složky

    return samples

def fft(signal):
    """Rychlá Fourierova transformace (FFT, rekurzivní verze)."""
    N = len(signal)
    if N <= 1:
        return signal

    even = fft(signal[0::2])  # Sudé indexy
    odd = fft(signal[1::2])   # Liché indexy

    T = [cmath.exp(-2j * math.pi * k / N) * odd[k] for k in range(N // 2)]
    return [even[k] + T[k] for k in range(N // 2)] + [even[k] - T[k] for k in range(N // 2)]

def measure_freq():
    """Najde dominantní frekvenci ve zvukovém signálu."""
    samples = get_samples()
    spectrum = fft(samples)

    magnitudes = [abs(c) for c in spectrum[:N // 2]]  # Pouze kladné frekvence
    peak_index = magnitudes.index(max(magnitudes))  # Najde nejvyšší frekvenci
    peak_freq = round(((peak_index * FS / N) / 2.05), 1)
    frekvence = peak_freq
    print(f"Dominantní frekvence je: {frekvence} Hz.")

    return frekvence
    
# CallMeBot API - nastavení odesílaných zpráv na WhatsApp

def send_whatsapp(number, api_key):
    message = "TEST+VČELY:+asi+si+balíme+baťůžky+a+mizíme+z+úlu!!!"
    url = f"https://api.callmebot.com/whatsapp.php?phone={number}&text={message}&apikey={api_key}"
    
    try:
        response = urequests.get(url)
        print("Odpověď serveru:", response.text)
        response.close()
    except Exception as e:
        print("Chyba:", e)
               

def deep_sleep(seconds):
    print("Přecházím do hlubokého spánku na 10 minut.")
    machine.deepsleep(seconds)
    
# Hlavní smyčka
connect_wifi()

# Inicializace instance pro aktualizaci
updater = update.Update(RAW_GITHUB_URL)

# Kontrola a aktualizace souboru main.py
updater.compare_and_update("main.py")

# načtení 'prázdné' váhy
first_weight = load_first_weight()

if first_weight is None:
    tare_value = hx.read_average(10)
    save_first_weight(tare_value)
else:
    tare_value = first_weight
    print(f"Používám první uloženou váhu: {tare_value}")


while True:
    try:
        # měření povětrnostních dat
        temp_aht, hum_aht, temp_bmp, pres_bmp = wheather_sensor_measure()
        # měření váhy
        weight = read_weight()
        # měření síly wifi
        rssi = get_wifi_signal_strength()
        # Měření frekvence
        

        prumer = []  # Definice seznamu pro průměr

        try:
            for _ in range(30):  # Cyklus poběží 50krát
                time.sleep(0.5)
                frekvence = measure_freq()  # Měření frekvence
                prumer.append(frekvence)  # Uložení do seznamu

            prum_frekvence = sum(prumer) / len(prumer)  # Výpočet průměru
            print(f"Průměrná frekvence: {prum_frekvence} Hz")

            if 350 < prum_frekvence < 500:  # Kontrola frekvence
                send_whatsapp("420733113537", "3142801")  # Pošle upozornění
                #send_whatsapp("420603498872", "4097369")  # Jirka
                print("Asi se rojíme")
    
            else:
                print("Vše OK")  # Pokud cyklus doběhne bez výstrahy
        except Exception as e:
            print("Chyba poslání notifikace:", e)

    # odeslání dat
        send_data(temp_aht, hum_aht, temp_bmp, pres_bmp, weight, rssi, prum_frekvence)
    except Exception as e:
        print("Chyba senzoru:", e)
     
    #time.sleep(20)
    deep_sleep(600000) # Hluboký spánek na 10 minut

