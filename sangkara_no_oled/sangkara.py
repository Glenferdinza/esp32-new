import gc
gc.enable()
gc.collect()
import network
wlan_sta = network.WLAN(network.STA_IF)
wlan_ap  = network.WLAN(network.AP_IF)
import time, json, random, urequests, machine
import usocket as socket
from machine import Pin, SoftI2C, PWM
from umqtt.simple import MQTTClient
def _patched_mqtt_connect(self, clean_session=True):
    print("[MQTT] Menjalankan patched connect...")
    self.sock = socket.socket()
    parts = self.server.split('.')
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        addr = (self.server, self.port)
    else:
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
    self.sock.connect(addr)
    premsg = bytearray(b"\x10\x00\x00\x04MQTT\x04\x02\x00\x00")
    msg = bytearray()
    if clean_session:
        premsg[11] |= 0x02
    if self.user is not None:
        premsg[11] |= 0x80
        if self.pswd is not None:
            premsg[11] |= 0x40
    cid = self.client_id.encode("utf-8") if isinstance(self.client_id, str) else self.client_id
    msg.append(len(cid) >> 8)
    msg.append(len(cid) & 0xFF)
    msg.extend(cid)
    if self.user is not None:
        u = self.user.encode("utf-8") if isinstance(self.user, str) else self.user
        msg.append(len(u) >> 8)
        msg.append(len(u) & 0xFF)
        msg.extend(u)
        if self.pswd is not None:
            p = self.pswd.encode("utf-8") if isinstance(self.pswd, str) else self.pswd
            msg.append(len(p) >> 8)
            msg.append(len(p) & 0xFF)
            msg.extend(p)
    premsg[1] = len(premsg) - 2 + len(msg)
    self.sock.write(premsg + msg)
    resp = self.sock.read(4)
    assert resp[0] == 0x20 and resp[1] == 0x02
    if resp[3] != 0:
        raise Exception(resp[3])
MQTTClient.connect = _patched_mqtt_connect

# ---------------------------------------------
#  KONFIGURASI UTAMA
#  YANG PERLU DIUBAH PER ALAT:
#  - KELOMPOK_ID  --> nomor kelompok (1, 2, 3, dst)
#  - WIFI_SSID    --> nama WiFi di lokasi
#  - WIFI_PASS    --> password WiFi
#  - MQTT_ID      --> harus unik per ESP32!
# ---------------------------------------------
KELOMPOK_ID = 1
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT   = 1883
MQTT_ID     = "esp32-sangkara-" + str(KELOMPOK_ID) + "-" + str(random.randint(1000,9999))
TOPIC_GAME    = b"sangkara/lidm26/game"
TOPIC_SOAL    = b"sangkara/lidm26/soal"
TOPIC_BTN     = b"sangkara/lidm26/button"
TOPIC_CMD     = b"sangkara/cmd"
TOPIC_MATERI  = b"sangkara/materi"
TOPIC_ALARM_GLOBAL  = b"sangkara/alarm/global"
TOPIC_ALARM_KLP     = ("sangkara/alarm/kelompok" + str(KELOMPOK_ID)).encode()
TOPIC_JAWABAN = b"sangkara/jawaban"
TOPIC_POSISI  = b"sangkara/posisi"
TOPIC_STATUS  = b"sangkara/status"
API_BASE = "https://lidm-api.irmajetson.my.id"
JUMLAH_PEMAIN = 4
NAMA_PEMAIN   = ["K1", "K2", "K3", "K4"]

# ---------------------------------------------
#  PIN MAP -- VERSI UTAMA TANPA OLED
# ---------------------------------------------
PIN_BUZZER = 16
PIN_LED = [23, 19, 18, 5]
PIN_BTN_A     = 26
PIN_BTN_B     = 27
PIN_BTN_C     = 14
PIN_BTN_D     = 13
PIN_BTN_DADU  = 4
PIN_BTN_RESET = 25
MAX_PETAK = 50
zona_list   = []
soal_pool   = {}
quotes_pool = []
jawaban_terpilih = set()
soal_dijawab = {}
soal_terpakai = {}

def cari_zona(posisi):
    """Cari zona berdasarkan posisi petak (1-50)"""
    for z in zona_list:
        if z.get("range_start", 0) <= posisi <= z.get("range_end", 0):
            return z
    return None

def ambil_soal_unik(zona_id, pos_lama=1, sisa_di_zona=50):
    try:
        url = "%s/iot/ambil-soal?zona_id=%s&pos_lama=%d&sisa_di_zona=%d&kelompok_id=%d&giliran=%d" % (
            API_BASE, zona_id, pos_lama, sisa_di_zona, KELOMPOK_ID, state["giliran"]
        )
        print("[HTTP] Ambil soal:", url)
        res = urequests.get(url, timeout=3.5)
        if res.status_code == 200:
            soal = res.json()
            res.close()
            g = state["giliran"]
            if g not in soal_terpakai:
                soal_terpakai[g] = set()
            soal_terpakai[g].add(soal.get("id", ""))
            return soal
        res.close()
    except Exception as e:
        print("[HTTP] Gagal ambil soal:", repr(e))
    return None

def ambil_quote(zona_id=""):
    global quotes_pool
    pilihan_global = quotes_pool.get("global", [])
    pilihan_zona = quotes_pool.get(zona_id, []) if zona_id else []
    kandidat = []
    for i, q in enumerate(pilihan_global):
        kandidat.append(("global", i, q))
    for i, q in enumerate(pilihan_zona):
        kandidat.append((zona_id, i, q))
    if not kandidat:
        return "Terus Melangkah, Jangan Menyerah!"
    key_sumber, idx, text = random.choice(kandidat)
    if key_sumber in quotes_pool:
        quotes_pool[key_sumber].pop(idx)
    return text

def init_tracking():
    """Reset tracking soal untuk game baru"""
    global soal_dijawab, soal_terpakai, studi_kasus_dilihat, riwayat_dadu
    soal_dijawab  = {i: set() for i in range(JUMLAH_PEMAIN)}
    soal_terpakai = {i: set() for i in range(JUMLAH_PEMAIN)}
    studi_kasus_dilihat = {i: set() for i in range(JUMLAH_PEMAIN)}
    riwayat_dadu  = {i: [] for i in range(JUMLAH_PEMAIN)}

def buat_state():
    return {
        "giliran":  0,
        "posisi":   [0] * JUMLAH_PEMAIN,
        "skor":     [0] * JUMLAH_PEMAIN,
        "dadu":     0,
        "fase":     "lempar",
        "pemenang": -1,
    }

state       = buat_state()
mqtt_client = None
soal_aktif = {
    "materi_id":    "",
    "soal_id":      "",
    "judul_materi": "",
    "soal":         "",
    "batas_waktu":  60,
    "jawaban_benar":"",
    "zona_id":      "",
    "studi_kasus_id": "",
}
studi_kasus_dilihat = {0: set(), 1: set(), 2: set(), 3: set()}
fase_membaca = False
riwayat_dadu = {0: [], 1: [], 2: [], 3: []}
soal_fase = 0
waktu_soal_mulai = 0
is_quotes = False

# ---------------------------------------------
#  HARDWARE INIT (MOCK OLED - NO PHYSICAL OLED REQUIRED)
# ---------------------------------------------
class MockOLED:
    def fill(self, val):
        pass
    def show(self):
        pass
    def text(self, txt, x, y, col=1):
        print("[DISPLAY] (%d,%d): %s" % (x, y, txt))
    def fill_rect(self, x, y, w, h, col):
        pass

oled = MockOLED()
buz  = Pin(PIN_BUZZER, Pin.OUT)
buz.value(0)
leds = [Pin(p, Pin.OUT) for p in PIN_LED]
btn_a     = Pin(PIN_BTN_A,     Pin.IN, Pin.PULL_UP)
btn_b     = Pin(PIN_BTN_B,     Pin.IN, Pin.PULL_UP)
btn_c     = Pin(PIN_BTN_C,     Pin.IN, Pin.PULL_UP)
btn_d     = Pin(PIN_BTN_D,     Pin.IN, Pin.PULL_UP)
btn_dadu  = Pin(PIN_BTN_DADU,  Pin.IN, Pin.PULL_UP)
btn_reset = Pin(PIN_BTN_RESET, Pin.IN, Pin.PULL_UP)
_last_key      = None
_last_key_time = 0

def baca_tombol():
    global _last_key, _last_key_time
    key = None
    if not btn_a.value():     key = 'A'
    elif not btn_b.value():   key = 'B'
    elif not btn_c.value():   key = 'C'
    elif not btn_d.value():   key = 'D'
    elif not btn_dadu.value():  key = 'DADU'
    elif not btn_reset.value(): key = 'RESET'
    now = time.ticks_ms()
    if key and key != _last_key and time.ticks_diff(now, _last_key_time) > 200:
        _last_key      = key
        _last_key_time = now
        return key
    if not key:
        _last_key = None
    return None

class _Timer:
    def off(self): pass
tm = _Timer()

def led_all_off():
    for l in leds: l.value(0)
def led_giliran():
    led_all_off()
    g = state["giliran"]
    if g < len(leds): leds[g].value(1)
def led_benar(idx):
    led_all_off()
    if idx < len(leds): leds[idx].value(1)
def led_flash_all(n=3, ms=150):
    for _ in range(n):
        for l in leds: l.value(1)
        time.sleep_ms(ms)
        led_all_off()
        time.sleep_ms(ms)

def beep(freq=800, ms=150, vol=512):
    if vol == 0 or freq <= 0:
        buz.value(0)
        return
    half_period = int(500000 / freq)
    period = half_period * 2
    pulse_high = min(int(period * 0.1), 30)
    pulse_low = period - pulse_high
    cycles = int((ms * 1000) / period)
    for _ in range(cycles):
        buz.value(1)
        time.sleep_us(pulse_high)
        buz.value(0)
        time.sleep_us(pulse_low)

def beep_ok():
    beep(700,80); time.sleep_ms(40); beep(1000,120)
def beep_wrong():
    beep(400,300)
def beep_maju():
    for f in [900,1100,1300]:
        beep(f,70); time.sleep_ms(30)
def beep_mundur():
    beep(600,120); time.sleep_ms(30); beep(350,200)
def beep_finish():
    for f in [800,1000,1200,1400,1600,1400,1600]:
        beep(f,90); time.sleep_ms(20)

is_alarm_active = False
def alarm_on():
    global is_alarm_active
    is_alarm_active = True
    for l in leds: l.value(1)
def alarm_off():
    global is_alarm_active
    is_alarm_active = False
    for l in leds: l.value(0)
    buz.value(0)

def o_clear():
    oled.fill(0); oled.show()
def o_header(judul, sub=""):
    oled.fill(0)
    oled.fill_rect(0,0,128,13,1)
    oled.text(judul[:16], 2, 3, 0)
    if sub: oled.text(sub[:16], 0, 17)
    oled.show()
def o_state():
    g = state["giliran"]
    oled.fill(0)
    oled.fill_rect(0,0,128,13,1)
    oled.text("KLP" + str(KELOMPOK_ID) + " SANGKARA", 8, 3, 0)
    oled.text("Giliran: " + NAMA_PEMAIN[g], 0, 16)
    oled.text("Posisi : %d/50" % state["posisi"][g], 0, 28)
    oled.text("Skor   : " + str(state["skor"][g]), 0, 40)
    oled.text("[DADU]  [A]-[D]", 0, 52)
    oled.show()
def o_dadu(angka):
    g = state["giliran"]
    oled.fill(0)
    oled.fill_rect(0,0,128,13,1)
    oled.text("DADU  " + NAMA_PEMAIN[g], 2, 3, 0)
    oled.text("Hasil : " + str(angka), 16, 20)
    oled.text("Posisi: " + str(state["posisi"][g]), 16, 34)
    oled.show()
def o_soal_tanya(soal_text):
    oled.fill(0)
    q_text = soal_text.split(" | A.", 1)[0] if " | A." in soal_text else soal_text
    words = q_text.split()
    baris, row = "", 0
    for w in words:
        if len(baris)+len(w)+1 > 16:
            oled.text(baris.rstrip(), 0, row*10)
            baris = w+" "; row += 1
            if row >= 6: break
        else:
            baris += w+" "
    if baris and row < 6:
        oled.text(baris.rstrip(), 0, row*10)
    oled.show()
def o_soal_opsi(soal_text, sel_set=None):
    oled.fill(0)
    opsi = []
    if " | A." in soal_text:
        parts = soal_text.split(" | A.", 1)
        o_text = parts[1]
        part_b = o_text.split(" B.")
        opt_a = "A." + part_b[0].strip()
        opt_b, opt_c, opt_d = "", "", ""
        if len(part_b) > 1:
            part_c = part_b[1].split(" C.")
            opt_b = "B." + part_c[0].strip()
            if len(part_c) > 1:
                part_d = part_c[1].split(" D.")
                opt_c = "C." + part_d[0].strip()
                if len(part_d) > 1:
                    opt_d = "D." + part_d[1].strip()
        opsi = [opt_a, opt_b, opt_c, opt_d]
    else:
        opsi = ["A. Opsi A", "B. Opsi B", "C. Opsi C", "D. Opsi D"]
    for i, opt in enumerate(opsi):
        if opt:
            char = chr(65 + i)
            if sel_set is not None and char in sel_set:
                oled.text("[*]" + opt[:13], 0, i*12)
            else:
                oled.text(opt[:16], 0, i*12)
    oled.fill_rect(0, 50, 128, 14, 1)
    if sel_set is not None:
        oled.text("DADU:KIRIM A-D:PILIH", 0, 53, 0)
    else:
        oled.text("TEKAN A/B/C/D", 12, 53, 0)
    oled.show()
def o_membaca_studi_kasus(text):
    oled.fill(0)
    words = text.split()
    baris, row = "", 0
    for w in words:
        if len(baris)+len(w)+1 > 16:
            oled.text(baris.rstrip(), 0, row*10)
            baris = w+" "; row += 1
            if row >= 5: break
        else:
            baris += w+" "
    if baris and row < 5:
        oled.text(baris.rstrip(), 0, row*10)
    oled.fill_rect(0, 52, 128, 12, 1)
    oled.text("[A-D] LANJUT", 16, 54, 0)
    oled.show()
def o_soal(soal_text):
    o_soal_tanya(soal_text)
def o_efek(baris1, baris2=""):
    oled.fill(0)
    x1 = max(0, (128 - len(baris1)*8) // 2)
    oled.text(baris1[:16], x1, 18)
    if baris2:
        x2 = max(0, (128 - len(baris2)*8) // 2)
        oled.text(baris2[:16], x2, 36)
    oled.show()

def kirim_posisi_api(only_active=False):
    positions = []
    g = state["giliran"]
    if only_active:
        positions.append({
            "kelompok_id": KELOMPOK_ID,
            "player_id":   g + 1,
            "position":    state["posisi"][g],
        })
    else:
        for i in range(JUMLAH_PEMAIN):
            positions.append({
                "kelompok_id": KELOMPOK_ID,
                "player_id":   i + 1,
                "position":    state["posisi"][i],
            })
    if mqtt_client:
        for p in positions:
            try:
                mqtt_client.publish(TOPIC_POSISI, json.dumps(p))
                time.sleep_ms(80)
            except:
                pass
    print("[POSISI] Terkirim untuk kelompok", KELOMPOK_ID)

def kirim_jawaban_api(jawaban, waktu_jawab):
    if not mqtt_client:
        return
    payload = {
        "materi_id":    soal_aktif.get("materi_id", ""),
        "soal_id":      soal_aktif.get("soal_id", ""),
        "jawaban":      jawaban,
        "waktu_jawab":  waktu_jawab,
        "batas_waktu":  soal_aktif.get("batas_waktu", 60),
        "judul_materi": soal_aktif.get("judul_materi", ""),
        "kasus_soal":   soal_aktif.get("soal", ""),
        "kelompok_id":  KELOMPOK_ID,
    }
    try:
        mqtt_client.publish(TOPIC_JAWABAN, json.dumps(payload))
        time.sleep_ms(50)
        print("[JAWABAN] Terkirim:", jawaban, "| waktu:", waktu_jawab, "s")
    except Exception as e:
        print("[JAWABAN] Gagal kirim:", e)

def kirim_status():
    if not mqtt_client:
        return
    payload = {
        "kelompok_id": KELOMPOK_ID,
        "status":      "online",
        "timestamp":   time.time(),
    }
    try:
        mqtt_client.publish(TOPIC_STATUS, json.dumps(payload))
        res = urequests.put(
            API_BASE + "/iot/kelompok/" + str(KELOMPOK_ID),
            headers={"Content-Type": "application/json"},
            data=json.dumps({"is_active": True}),
            timeout=2.0
        )
        res.close()
    except:
        pass

def on_message(topic, msg):
    print("[MQTT] Pesan masuk pada:", topic.decode() if isinstance(topic, bytes) else topic, "ukuran:", len(msg), "bytes")
    global soal_aktif, waktu_soal_mulai
    txt = msg.decode()
    if topic == TOPIC_ALARM_GLOBAL or topic == TOPIC_ALARM_KLP:
        try:
            d = json.loads(txt)
            if d.get("action") == "activate" or d.get("alarm") == "on":
                alarm_on()
            else:
                alarm_off()
        except:
            if msg == b"ON":
                alarm_on()
            else:
                alarm_off()
    elif topic == TOPIC_SOAL:
        try:
            d = json.loads(txt)
            soal_aktif["materi_id"]     = d.get("materi_id", "")
            soal_aktif["soal_id"]       = d.get("soal_id", "")
            soal_aktif["judul_materi"]  = d.get("judul_materi", d.get("judul", "SOAL"))
            soal_aktif["soal"]          = d.get("soal", d.get("kasus_soal", ""))
            soal_aktif["batas_waktu"]   = int(d.get("batas_waktu", 60))
            soal_aktif["jawaban_benar"] = d.get("jawaban_benar", "")
            soal_aktif["zona_id"]       = d.get("zona_id", "")
            waktu_soal_mulai = time.time()
            global soal_fase
            soal_fase = 1
            o_soal_tanya(soal_aktif["soal"])
            beep(800, 100)
        except Exception as e:
            print("[SOAL] Parse error:", e)
            o_soal(txt)
    elif topic == TOPIC_CMD:
        try:
            d = json.loads(txt)
            if d.get("cmd") == "reset":
                reset_game()
        except:
            pass
    elif topic == TOPIC_MATERI:
        try:
            d = json.loads(txt)
            global zona_list, soal_pool, quotes_pool
            target_groups = d.get("target_groups", [])
            if target_groups and len(target_groups) > 0:
                if KELOMPOK_ID not in target_groups:
                    print("[MATERI] Diabaikan. Bukan untuk kelompok ini.")
                    return
            zona_list = d.get("zona", [])
            soal_pool = {}
            quotes_pool = {"global": []}
            soal_aktif["materi_id"]    = d.get("materi_id", "")
            soal_aktif["judul_materi"] = d.get("judul_materi", "")
            print("[MATERI] Zona dimuat:", len(zona_list), "zona")
            for s in d.get("soal", []):
                zid = s.get("zona_id", "")
                if zid not in soal_pool:
                    soal_pool[zid] = []
                soal_pool[zid].append(s)
            total_soal = sum(len(v) for v in soal_pool.values())
            print("[MATERI] Soal dimuat:", total_soal, "soal")
            for q in d.get("quotes", []):
                if q.startswith("[") and "]" in q:
                    parts = q.split("]", 1)
                    zid = parts[0][1:]
                    text = parts[1].strip()
                    if zid not in quotes_pool: quotes_pool[zid] = []
                    quotes_pool[zid].append(text)
                else:
                    quotes_pool["global"].append(q)
            total_q = sum(len(v) for v in quotes_pool.values())
            print("[MATERI] Quotes dimuat:", total_q, "quotes")
            init_tracking()
            if state["fase"] == "jawab":
                g = state["giliran"]
                pos = state["posisi"][g]
                zona = cari_zona(pos)
                if zona:
                    zona_id = zona.get("id", "")
                    range_end = int(zona.get("range_end", MAX_PETAG))
                    sisa_di_zona = range_end - pos
                    soal = ambil_soal_unik(zona_id, pos, sisa_di_zona)
                    if soal:
                        soal_aktif["zona_id"]       = zona_id
                        soal_aktif["soal_id"]       = soal.get("id", "")
                        soal_aktif["soal"]          = soal.get("soal", soal.get("kasus_soal", ""))
                        soal_aktif["jawaban_benar"] = soal.get("jawaban_benar", "")
                        soal_aktif["batas_waktu"]   = int(soal.get("batas_waktu", 60))
                        sc_id = soal.get("studi_kasus_id", "")
                        sc_text = soal.get("studi_kasus_text", "")
                        soal_aktif["studi_kasus_id"] = sc_id
                        waktu_soal_mulai = time.time()
                        if sc_id and sc_id not in studi_kasus_dilihat.get(g, set()):
                            global fase_membaca
                            fase_membaca = True
                            if mqtt_client:
                                try:
                                    mqtt_client.publish(b"sangkara/membaca", json.dumps({
                                        "kelompok_id": KELOMPOK_ID,
                                        "player_id": g + 1,
                                        "status": "reading"
                                    }))
                                except:
                                    pass
                            o_membaca_studi_kasus(sc_text)
                        else:
                            global fase_membaca, soal_fase
                            fase_membaca = False
                            soal_fase = 1
                            o_soal_tanya(soal_aktif["soal"])
                            pub_state("landing_soal")
                    else:
                        global is_quotes
                        is_quotes = True
                        quote = ambil_quote(zona_id)
                        o_soal(quote)
                        pub_state("quotes")
                        next_turn()
            o_header("MATERI OK", d.get("judul_materi", "")[:16])
            beep_ok()
            time.sleep(1)
            o_state()
        except Exception as e:
            print("[MATERI] Parse error:", repr(e))

def pub_state(event="update"):
    if not mqtt_client: return
    try:
        mqtt_client.publish(TOPIC_GAME, json.dumps({
            "event":       event,
            "kelompok_id": KELOMPOK_ID,
            "giliran":     state["giliran"],
            "nama":        NAMA_PEMAIN[state["giliran"]],
            "posisi":      state["posisi"],
            "skor":        state["skor"],
            "dadu":        state["dadu"],
            "fase":        state["fase"],
            "pemenang":    state["pemenang"],
        }))
    except Exception as e:
        print("Pub error:", e)

def load_wifi_config():
    try:
        with open("wifi_config.json", "r") as f:
            return json.loads(f.read())
    except:
        return None

def save_wifi_config(ssid, pwd):
    with open("wifi_config.json", "w") as f:
        f.write(json.dumps({"ssid": ssid, "password": pwd}))

def unquote(s):
    res = s.replace('+', ' ')
    parts = res.split('%')
    out = parts[0]
    for p in parts[1:]:
        if len(p) >= 2:
            try:
                out += chr(int(p[:2], 16)) + p[2:]
            except:
                out += '%' + p
        else:
            out += '%' + p
    return out

def captive_portal():
    print("[NET] Memulai Captive Portal (Mode Konfigurasi)...")
    try:
        wlan_sta.disconnect()
        wlan_sta.active(False)
    except:
        pass
    time.sleep(1)
    import gc
    gc.collect()
    try:
        wlan_ap.active(True)
        time.sleep_ms(500)
        wlan_ap.config(essid="SANGKARA-KLP" + str(KELOMPOK_ID), authmode=0)
    except Exception as e:
        print("AP init error:", e)
    o_header("WiFi Config", "Buka 192.168.4.1")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    for _ in range(5):
        try:
            s.bind(('', 80))
            break
        except OSError as e:
            print("Bind port 80 failed, retrying...", e)
            time.sleep_ms(500)
    s.listen(1)
    s.settimeout(0.1)
    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        udps.bind(('0.0.0.0', 53))
        udps.settimeout(0.1)
        print("[DNS] Server Portal Siap di 192.168.4.1 (DNS non-blocking)")
    except Exception as e:
        print("[DNS] Bind port 53 error:", e)
    failed_attempts = {}
    while True:
        check_wifi_reset_anytime()
        try:
            data, addr = udps.recvfrom(1024)
            packet = data[:2] + b'\x81\x80' + data[4:6] + data[4:6] + b'\x00\x00\x00\x00'
            idx = 12
            while data[idx] != 0:
                idx += data[idx] + 1
            idx += 5
            packet += data[12:idx]
            packet += b'\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x0a\x00\x04\xc0\xa8\x04\x01'
            udps.sendto(packet, addr)
        except OSError:
            pass
        try:
            conn, addr = s.accept()
            conn.settimeout(1.0)
        except OSError:
            continue
        except:
            time.sleep_ms(50)
            continue
        try:
            req = conn.recv(1024)
            req_str = req.decode('utf-8', 'ignore')
            if req_str:
                print("[HTTP] Request dari", addr, ":", req_str.split("\n")[0].strip())
        except OSError:
            try:
                conn.close()
            except:
                pass
            continue
        if not req_str:
            try:
                conn.close()
            except:
                pass
            continue
        if "GET " in req_str and "192.168.4.1" not in req_str:
            try:
                print("[HTTP] Redirecting", addr, "to 192.168.4.1")
                conn.send(b'HTTP/1.1 302 Found\r\nLocation: http://192.168.4.1/\r\nConnection: close\r\n\r\n')
            except Exception as e:
                print("[HTTP] Send redirect error:", e)
            try:
                conn.close()
            except:
                pass
            continue
        def send_html(html_body):
            try:
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n')
                conn.send(b'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">')
                conn.send(b'<style>*{box-sizing:border-box;}body{font-family:sans-serif;background:#f0f2f5;margin:0;padding:20px;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:90vh;}.container{background:white;padding:30px;border-radius:12px;box-shadow:0 8px 24px rgba(30,58,95,0.08);width:100%;max-width:360px;text-align:center;}h1{color:#1E3A5F;font-size:28px;margin:0 0 20px 0;}.container svg{width:100%;height:auto;max-height:80px;margin:0 0 20px 0;}h3{color:#333;margin:0 0 15px 0;font-size:18px;}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ccc;border-radius:6px;font-size:16px;outline:none;}input:focus{border-color:#1E3A5F;}button{width:100%;padding:12px;color:white;border:none;border-radius:6px;font-weight:bold;font-size:16px;cursor:pointer;margin-top:10px;}</style></head>')
                conn.send(b'<body><div class="container">')
                conn.send(b'<h1>SANGKARA</h1>')
                if isinstance(html_body, str):
                    conn.send(html_body.encode('utf-8'))
                else:
                    conn.send(html_body)
                conn.send(b'</div><script>var eyeOpen=`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;var eyeClosed=`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;function togglePass(id,el){var x=document.getElementById(id);if(x.type==="password"){x.type="text";el.innerHTML=eyeClosed;}else{x.type="password";el.innerHTML=eyeOpen;}}</script></body></html>')
            except Exception as e:
                print("HTML send error:", e)
            finally:
                try:
                    conn.close()
                except:
                    pass
        try:
            client_ip = addr[0]
            if client_ip in failed_attempts and failed_attempts[client_ip] >= 3:
                send_html('<h3 style="color:#C0392B;">Akses Ditangguhkan</h3><p style="color:#666;font-size:14px;margin:10px 0 20px 0;">Anda telah salah memasukkan sandi sebanyak 3 kali. Akses ke halaman konfigurasi dinonaktifkan sementara demi keamanan.</p>')
                continue
            if "POST /login " in req_str:
                parts = req_str.split("\r\n\r\n")
                if len(parts) < 2:
                    parts = req_str.split("\n\n")
                body = parts[-1] if len(parts) >= 2 else ""
                if "sangkaraadmin123" in body or "admin_pass=sangkaraadmin123" in body:
                    failed_attempts[client_ip] = 0
                    send_html('''<h3>Konfigurasi WiFi</h3>
                    <form method="POST" action="/save" style="margin:0;">
                    <input type="text" name="ssid" placeholder="Nama WiFi (SSID)" required><br>
                    <div style="position:relative;width:100%;margin:10px 0;">
                        <input type="password" id="wifi_pass" name="password" placeholder="Password WiFi" style="padding-right:40px;margin:0;">
                        <span onclick="togglePass('wifi_pass', this)" style="position:absolute;right:12px;top:50%;transform:translateY(-50%);cursor:pointer;display:flex;align-items:center;user-select:none;"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg></span>
                    </div>
                    <button type="submit" style="background:#27AE60;">Simpan & Restart</button>
                    </form>''')
                else:
                    failed_attempts[client_ip] = failed_attempts.get(client_ip, 0) + 1
                    attempts = failed_attempts[client_ip]
                    if attempts >= 3:
                        send_html('<h3 style="color:#C0392B;">Akses Ditangguhkan</h3><p style="color:#666;font-size:14px;margin:10px 0 20px 0;">Anda telah salah memasukkan sandi sebanyak 3 kali. Akses ke halaman konfigurasi dinonaktifkan sementara demi keamanan.</p>')
                    else:
                        send_html('''<h3>Login Admin</h3>
                        <form method="POST" action="/login" style="margin:0;">
                        <div style="position:relative;width:100%;margin:10px 0;">
                            <input type="password" id="pass_field" name="admin_pass" placeholder="Password Admin" style="padding-right:40px;margin:0;" required>
                            <span onclick="togglePass('pass_field', this)" style="position:absolute;right:12px;top:50%;transform:translateY(-50%);cursor:pointer;display:flex;align-items:center;user-select:none;"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg></span>
                        </div>
                        <p style="color:#C0392B;font-size:14px;margin:10px 0 0 0;">Sandi salah, silakan coba kembali.</p>
                        <button type="submit" style="background:#1E3A5F;margin-top:15px;">Login</button>
                        </form>''')
            elif "POST /save " in req_str:
                parts = req_str.split("\r\n\r\n")
                if len(parts) < 2:
                    parts = req_str.split("\n\n")
                body = parts[-1] if len(parts) >= 2 else ""
                params = {}
                for p in body.split('&'):
                    if '=' in p:
                        k, v = p.split('=', 1)
                        params[k] = v
                ssid = unquote(params.get("ssid", ""))
                pwd = unquote(params.get("password", ""))
                save_wifi_config(ssid, pwd)
                send_html(f'''<h3 style="color:#27AE60;">Berhasil Disimpan!</h3>
                <p style="color:#666;font-size:14px;margin:10px 0 0 0;">
                ESP32 me-restart untuk tersambung ke jaringan <b>{ssid}</b>.<br><br>
                Halaman ini akan tertutup otomatis dalam <span id="t" style="font-weight:bold;color:#27AE60;">5</span> detik...
                </p>
                <p style="color:#999;font-size:12px;margin:15px 0 0 0;font-style:italic;">
                Jika halaman tidak tertutup, silakan tutup tab ini secara manual.
                </p>
                <script>
                history.pushState(null, null, location.href);
                window.onpopstate = function () {{
                    history.pushState(null, null, location.href);
                }};
                var c=5;
                var i=setInterval(function(){{
                    c--;
                    document.getElementById("t").textContent=c;
                    if(c<=0){{
                        clearInterval(i);
                        window.open('', '_self', '');
                        window.close();
                    }}
                }},1000);
                </script>''')
                time.sleep(3)
                try:
                    s.close()
                    udps.close()
                except:
                    pass
                machine.reset()
            else:
                send_html('''<h3>Login Admin</h3>
                <form method="POST" action="/login" style="margin:0;">
                <div style="position:relative;width:100%;margin:10px 0;">
                    <input type="password" id="pass_field" name="admin_pass" placeholder="Password Admin" style="padding-right:40px;margin:0;" required>
                    <span onclick="togglePass('pass_field', this)" style="position:absolute;right:12px;top:50%;transform:translateY(-50%);cursor:pointer;display:flex;align-items:center;user-select:none;"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg></span>
                </div>
                <button type="submit" style="background:#1E3A5F;margin-top:15px;">Login</button>
                </form>''')
        except Exception as e:
            print("Request processing error:", e)
            try:
                conn.close()
            except:
                pass

def check_wifi_reset_anytime():
    if not btn_dadu.value():
        t_start = time.ticks_ms()
        shown_prompt = False
        while not btn_dadu.value():
            diff = time.ticks_diff(time.ticks_ms(), t_start)
            if diff > 500 and not shown_prompt:
                o_efek("Tahan...", "reset WiFi")
                shown_prompt = True
            if diff > 3000:
                import os
                try:
                    os.remove("wifi_config.json")
                except:
                    pass
                try:
                    wlan_sta.active(True)
                    wlan_sta.disconnect()
                    wlan_sta.active(False)
                except:
                    pass
                o_efek("WIFI DIHAPUS", "Restarting...")
                beep(600, 500)
                time.sleep(1)
                machine.reset()
            time.sleep_ms(50)

def connect_wifi():
    import gc
    gc.collect()
    check_wifi_reset_anytime()
    if wlan_sta.isconnected():
        print("[NET] Wi-Fi terdeteksi sudah terkoneksi via boot.py")
        o_header("WiFi OK", wlan_sta.ifconfig()[0])
        time.sleep(1)
        return True
    conf = load_wifi_config()
    if not conf:
        captive_portal()
        return False
    o_header("SANGKARA", "Konek WiFi...")
    wlan_sta.active(True)
    wlan_sta.connect(conf["ssid"], conf["password"])
    t = 150
    while not wlan_sta.isconnected() and t > 0:
        check_wifi_reset_anytime()
        time.sleep_ms(100)
        t -= 1
    if wlan_sta.isconnected():
        o_header("WiFi OK", wlan_sta.ifconfig()[0])
        time.sleep(1)
        wlan_ap.active(False)
        return True
    o_header("WiFi GAGAL!", "Masuk Config Mode")
    time.sleep(2)
    captive_portal()
    return False

def deteksi_mode_jaringan():
    global API_BASE, MQTT_BROKER
    if not wlan_sta.isconnected():
        return
    try:
        cfg = None
        try:
            with open("wifi_config.json", "r") as f:
                cfg = json.loads(f.read())
        except:
            pass
        current_ssid = cfg.get("ssid", "") if cfg else ""
    except:
        current_ssid = ""
    if current_ssid == "Sangkara-Net":
        print("[NET] SSID Sangkara-Net terdeteksi. Langsung masuk MODE OFFLINE.")
        try:
            info = wlan_sta.ifconfig()
            gateway = info[2]
            if gateway and gateway != "0.0.0.0":
                API_BASE = "http://" + gateway + ":4001"
                MQTT_BROKER = gateway
                print("[NET] Mode Offline Lokal Aktif. Server:", API_BASE, "| MQTT:", gateway)
                o_header("MODE OFFLINE", "Server: " + gateway)
            else:
                raise ValueError("Gateway tidak valid")
        except Exception as e:
            API_BASE = "http://10.42.0.1:4001"
            MQTT_BROKER = "10.42.0.1"
            o_header("MODE OFFLINE", "Server: 10.42.0.1")
            print("[NET] Fallback default offline:", e)
        time.sleep(1)
        return
    print("[NET] Mengecek konektivitas internet...")
    o_header("SANGKARA", "Cek Internet...")
    broker_online = "broker.hivemq.com"
    api_online = "https://lidm-api.irmajetson.my.id"
    is_online = False
    try:
        import usocket
        addr_info = usocket.getaddrinfo("broker.hivemq.com", 1883)[0][-1]
        s = usocket.socket()
        s.settimeout(3)
        s.connect(addr_info)
        s.close()
        is_online = True
        print("[NET] Terdeteksi ONLINE. DNS resolve & TCP connect sukses.")
    except Exception as e:
        print("[NET] Gagal koneksi ke internet:", e)
    if is_online:
        API_BASE = api_online
        MQTT_BROKER = broker_online
        o_header("MODE ONLINE", "Cloud Server")
        print("[NET] Mode Online Aktif. API:", API_BASE)
        time.sleep(1)
        return
    print("[NET] Gagal terhubung ke internet. Mengaktifkan MODE OFFLINE LOKAL.")
    try:
        info = wlan_sta.ifconfig()
        gateway = info[2]
        if gateway and gateway != "0.0.0.0":
            API_BASE = "http://" + gateway + ":4001"
            MQTT_BROKER = gateway
            print("[NET] Mode Offline Lokal Aktif. Server:", API_BASE, "| MQTT:", gateway)
            o_header("MODE OFFLINE", "Server: " + gateway)
        else:
            raise ValueError("Gateway tidak valid: " + str(gateway))
    except Exception as e:
        API_BASE = "http://192.168.1.1:4001"
        MQTT_BROKER = "192.168.1.1"
        o_header("MODE OFFLINE", "Server: 192.168.1.1")
        print("[NET] Fallback default offline:", e)
    time.sleep(1)

def connect_mqtt(silent=False):
    global mqtt_client
    if not silent:
        o_header("KLP" + str(KELOMPOK_ID), "Konek MQTT...")
        time.sleep(1.5)
    try:
        import gc
        gc.collect()
        print("[MQTT] Free memory sebelum konek:", gc.mem_free())
        import usocket
        broker = MQTT_BROKER
        cid = MQTT_ID.encode() if isinstance(MQTT_ID, str) else MQTT_ID
        print("[MQTT] Memulai koneksi ke %s:%d dengan Client ID: %s..." % (broker, MQTT_PORT, MQTT_ID))
        s = usocket.socket()
        s.connect((broker, MQTT_PORT))
        time.sleep_ms(200)
        premsg = bytearray(b"\x10\x00\x00\x04MQTT\x04\x02\x00\x3c")
        msg = bytearray()
        msg.append(len(cid) >> 8)
        msg.append(len(cid) & 0xFF)
        msg.extend(cid)
        premsg[1] = len(premsg) - 2 + len(msg)
        payload = bytes(premsg + msg)
        print("[MQTT] Menulis payload CONNECT (%d bytes)..." % len(payload))
        s.write(payload)
        print("[MQTT] CONNECT terkirim, menunggu CONNACK...")
        resp = s.read(4)
        if not resp or resp[0] != 0x20 or resp[3] != 0:
            s.close()
            raise Exception("CONNACK gagal: " + str(resp))
        c = MQTTClient(MQTT_ID, broker, port=MQTT_PORT, keepalive=60)
        c.sock = s
        c.set_callback(on_message)
        for t in [TOPIC_SOAL, TOPIC_ALARM_GLOBAL, TOPIC_ALARM_KLP, TOPIC_CMD, TOPIC_MATERI]:
            c.subscribe(t)
        mqtt_client = c
        if not silent:
            o_header("MQTT OK", "Kelompok " + str(KELOMPOK_ID))
            beep_ok()
            time.sleep(1)
        print("[MQTT] Koneksi berhasil ke", broker)
        return True
    except Exception as e:
        print("MQTT err:", e)
        if not silent:
            o_header("MQTT GAGAL")
        return False

def reset_game():
    global state, soal_aktif, waktu_soal_mulai, is_quotes
    state = buat_state()
    soal_aktif = {
        "materi_id": "", "soal_id": "",
        "judul_materi": "", "soal": "",
        "batas_waktu": 60, "jawaban_benar": ""
    }
    waktu_soal_mulai = 0
    is_quotes = False
    init_tracking()
    tm.off()
    led_giliran()
    o_state()
    pub_state("reset")
    kirim_posisi_api()

def lempar_dadu():
    global is_quotes, waktu_soal_mulai, soal_fase
    if state["fase"] != "lempar" or state["pemenang"] >= 0:
        return
    g = state["giliran"]
    is_quotes = False
    beep(600, 50)
    history = riwayat_dadu.get(g, [])
    while True:
        angka = random.randint(1, 4)
        if len(history) >= 2 and history[-1] == angka and history[-2] == angka:
            continue
        break
    history.append(angka)
    if len(history) > 2:
        history.pop(0)
    riwayat_dadu[g] = history
    delays = [0.03, 0.03, 0.03, 0.03, 0.05, 0.05, 0.05, 0.1, 0.1, 0.15, 0.25]
    for d in delays:
        temp_angka = random.randint(1, 4)
        o_efek("Mengocok Dadu", f"    [ {temp_angka} ]")
        beep(700, 15)
        time.sleep(d)
    state["dadu"] = angka
    o_efek("Hasil Dadu", f"   >> {angka} <<")
    beep_ok()
    time.sleep(1.5)
    pos_lama = state["posisi"][g]
    pos_baru = min(pos_lama + angka, MAX_PETAK)
    state["posisi"][g] = pos_baru
    kirim_posisi_api(only_active=True)
    if pos_baru >= MAX_PETAK:
        state["pemenang"] = g
        state["fase"] = "selesai"
        o_efek("MENANG!", NAMA_PEMAIN[g])
        led_flash_all(5)
        beep_finish()
        pub_state("selesai")
        return
    zona = cari_zona(pos_baru)
    zona_id = zona.get("id", "") if zona else ""
    zona_nama = zona.get("nama", "???") if zona else "???"
    sudah_jawab_zona = zona_id in soal_dijawab.get(g, set())
    if not sudah_jawab_zona and zona_id:
        range_end = int(zona.get("range_end", MAX_PETAK))
        sisa_di_zona = range_end - pos_baru
        if pos_lama == 0 or sisa_di_zona <= 6:
            peluang_soal = 1.0
        else:
            peluang_soal = 0.90
        if random.random() < peluang_soal:
            soal = ambil_soal_unik(zona_id, pos_lama, sisa_di_zona)
            if soal:
                state["fase"] = "jawab"
                soal_aktif["zona_id"]       = zona_id
                soal_aktif["soal_id"]       = soal.get("id", "")
                soal_aktif["soal"]          = soal.get("soal", soal.get("kasus_soal", ""))
                soal_aktif["jawaban_benar"] = soal.get("jawaban_benar", "")
                soal_aktif["batas_waktu"]   = int(soal.get("batas_waktu", 60))
                sc_id = soal.get("studi_kasus_id", "")
                sc_text = soal.get("studi_kasus_text", "")
                soal_aktif["studi_kasus_id"] = sc_id
                if sc_id and sc_id not in studi_kasus_dilihat.get(g, set()):
                    global fase_membaca, waktu_soal_mulai
                    fase_membaca = True
                    waktu_soal_mulai = time.time()
                    if mqtt_client:
                        try:
                            mqtt_client.publish(b"sangkara/membaca", json.dumps({
                                "kelompok_id": KELOMPOK_ID,
                                "player_id": g + 1,
                                "status": "reading"
                            }))
                        except:
                            pass
                    o_membaca_studi_kasus(sc_text)
                    beep(800, 150)
                    pub_state("membaca_soal")
                    print("[SOAL] Pion", NAMA_PEMAIN[g], "membaca kasus:", sc_id)
                    return
                else:
                    global fase_membaca, waktu_soal_mulai, soal_fase
                    fase_membaca = False
                    waktu_soal_mulai = time.time()
                    soal_fase = 1
                    o_soal_tanya(soal_aktif["soal"])
                    beep(800, 100)
                    pub_state("landing_soal")
                    print("[SOAL]", NAMA_PEMAIN[g], "zona:", zona_nama,
                          "| soal:", soal_aktif["soal_id"])
                    return
    is_quotes = True
    quote = ambil_quote(zona_id)
    o_soal(quote)
    beep(500, 100)
    print("[QUOTES]", NAMA_PEMAIN[g], "zona:", zona_nama, "|", quote[:30])
    time.sleep(3)
    pub_state("quotes")
    next_turn()

def proses_jawaban(klp_char):
    global is_quotes
    if state["fase"] != "jawab":
        return
    if is_quotes:
        return
    g = state["giliran"]
    benar = soal_aktif.get("jawaban_benar", "")
    waktu_jawab = int(time.time() - waktu_soal_mulai) if waktu_soal_mulai else 0
    beep(700, 80)
    if klp_char in NAMA_PEMAIN:
        idx = NAMA_PEMAIN.index(klp_char)
        led_benar(idx)
    if mqtt_client:
        try:
            mqtt_client.publish(TOPIC_BTN, json.dumps({
                "kelompok_id": KELOMPOK_ID,
                "kelompok":    klp_char,
                "posisi":      state["posisi"][g],
                "giliran":     NAMA_PEMAIN[g],
            }))
        except:
            pass
    kirim_jawaban_api(klp_char, waktu_jawab)
    if benar is None:
        benar = ""
    if benar.startswith("Opsi "):
        benar = benar[-1].upper()
    else:
        benar = benar.upper()
    klp_char = klp_char.upper()
    is_benar = False
    if benar and klp_char == benar:
        is_benar = True
        state["skor"][g] += 10
        pos_bonus = min(state["posisi"][g] + 1, MAX_PETAK)
        state["posisi"][g] = pos_bonus
        o_efek("BENAR! +1", "Pos: " + str(pos_bonus))
        beep_ok()
        print("[JAWAB] BENAR!", NAMA_PEMAIN[g], "-> pos", pos_bonus)
    elif benar:
        pos_penalty = max(state["posisi"][g] - 2, 1)
        state["posisi"][g] = pos_penalty
        o_efek("SALAH! -2", "Pos: " + str(pos_penalty))
        beep_wrong()
        print("[JAWAB] SALAH!", NAMA_PEMAIN[g], "-> pos", pos_penalty)
    else:
        o_efek("Jawab: " + klp_char, "Menunggu...")
        beep(800, 100)
    if is_benar:
        zid = soal_aktif.get("zona_id", "")
        if zid:
            if g in soal_dijawab:
                soal_dijawab[g].add(zid)
            sid = soal_aktif.get("soal_id", "")
            if g in soal_terpakai and sid:
                soal_terpakai[g].add(sid)
    kirim_posisi_api(only_active=True)
    if state["posisi"][g] >= MAX_PETAK:
        state["pemenang"] = g
        state["fase"] = "selesai"
        o_efek("MENANG!", NAMA_PEMAIN[g])
        led_flash_all(5)
        beep_finish()
        pub_state("selesai")
        return
    time.sleep(2)
    pub_state("jawaban")
    next_turn()

def next_turn():
    state["fase"]    = "lempar"
    state["giliran"] = (state["giliran"] + 1) % JUMLAH_PEMAIN
    tm.off()
    led_giliran()
    o_state()
    pub_state("next_turn")

def main():
    global mqtt_client, waktu_soal_mulai, fase_membaca, soal_fase
    o_header("SANGKARA", "Kelompok " + str(KELOMPOK_ID))
    time.sleep(1)
    connect_wifi()
    deteksi_mode_jaringan()
    connect_mqtt()
    kirim_status()
    reset_game()
    print("[SANGKARA] Kelompok", KELOMPOK_ID, "- Loop berjalan")
    last_heartbeat = time.time()
    last_sisa_waktu = -1
    last_mqtt_reconnect = 0
    mqtt_reconnect_interval = 15
    while True:
        import gc
        gc.collect()
        if mqtt_client:
            try:
                mqtt_client.check_msg()
            except Exception as e:
                print("check_msg error:", e)
                mqtt_client = None
                last_mqtt_reconnect = time.time()
                mqtt_reconnect_interval = 15
        else:
            now_time = time.time()
            if now_time - last_mqtt_reconnect > mqtt_reconnect_interval:
                last_mqtt_reconnect = now_time
                print("[MQTT] Mencoba koneksi ulang (interval %d detik)..." % mqtt_reconnect_interval)
                if connect_mqtt(silent=True):
                    mqtt_reconnect_interval = 15
                else:
                    mqtt_reconnect_interval = min(mqtt_reconnect_interval * 2, 300)
        if is_alarm_active:
            beep(1500, 100)
            time.sleep_ms(100)
            continue
        if time.time() - last_heartbeat > 30:
            kirim_status()
            last_heartbeat = time.time()
        if state["fase"] == "jawab" and not is_quotes and waktu_soal_mulai > 0 and not fase_membaca:
            berjalan = time.time() - waktu_soal_mulai
            batas = soal_aktif.get("batas_waktu", 60)
            waktu_tanya = int(batas * 2 / 3)
            if berjalan < waktu_tanya:
                if soal_fase != 1:
                    soal_fase = 1
                    o_soal_tanya(soal_aktif["soal"])
            elif berjalan < waktu_tanya + 2:
                if soal_fase != 2:
                    soal_fase = 2
                    o_efek("Saatnya...", "Menjawab!")
                    beep(800, 100)
            else:
                if soal_fase != 3:
                    soal_fase = 3
                    is_multi = len(soal_aktif.get("jawaban_benar", "")) > 1
                    if is_multi:
                        global jawaban_terpilih
                        jawaban_terpilih.clear()
                        o_soal_opsi(soal_aktif["soal"], jawaban_terpilih)
                    else:
                        o_soal_opsi(soal_aktif["soal"])
                sisa = (batas + 2) - berjalan
                if 0 < sisa <= 10:
                    if int(sisa) != last_sisa_waktu:
                        last_sisa_waktu = int(sisa)
                        beep(1000, 50)
                if sisa <= 0:
                    print("[TIMEOUT] Waktu habis untuk player", NAMA_PEMAIN[state["giliran"]])
                    o_efek("WAKTU HABIS!", "Dianggap SALAH")
                    beep(500, 500)
                    time.sleep(1)
                    proses_jawaban("TIMEOUT")
        key = baca_tombol()
        if key:
            print("[KEY]", key)
            if fase_membaca:
                if key in ('A', 'B', 'C', 'D'):
                    fase_membaca = False
                    studi_kasus_dilihat[state["giliran"]].add(soal_aktif["studi_kasus_id"])
                    beep(900, 80)
                    time.sleep_ms(40)
                    beep(1100, 80)
                    if mqtt_client:
                        try:
                            mqtt_client.publish(b"sangkara/membaca", json.dumps({
                                "kelompok_id": KELOMPOK_ID,
                                "player_id": state["giliran"] + 1,
                                "status": "answering"
                            }))
                        except:
                            pass
                    waktu_soal_mulai = time.time()
                    soal_fase = 1
                    o_soal_tanya(soal_aktif["soal"])
                else:
                    print("[KEY] Diabaikan. Tekan A-D untuk lanjut ke soal kuis.")
            else:
                if key in ('#', 'DADU'):
                    t_start = time.ticks_ms()
                    is_long_press = False
                    shown_prompt = False
                    while not btn_dadu.value():
                        diff = time.ticks_diff(time.ticks_ms(), t_start)
                        if diff > 500 and not shown_prompt:
                            o_efek("Tahan...", "reset WiFi")
                            shown_prompt = True
                        if diff > 3000:
                            is_long_press = True
                            break
                        time.sleep_ms(50)
                    if is_long_press:
                        import os
                        try:
                            os.remove("wifi_config.json")
                        except:
                            pass
                        try:
                            wlan_sta.active(True)
                            wlan_sta.disconnect()
                            wlan_sta.active(False)
                        except:
                            pass
                        o_efek("WIFI DIHAPUS", "Restarting...")
                        beep(600, 500)
                        time.sleep(1)
                        machine.reset()
                    else:
                        is_multi = len(soal_aktif.get("jawaban_benar", "")) > 1
                        if state["fase"] == "jawab" and not is_quotes and is_multi:
                            global jawaban_terpilih
                            if len(jawaban_terpilih) == 0:
                                beep(400, 150)
                            else:
                                ans = "".join(sorted(list(jawaban_terpilih)))
                                proses_jawaban(ans)
                        elif state["fase"] == "lempar" and state["pemenang"] < 0:
                            lempar_dadu()
                        else:
                            o_state()
                elif key in ('*', 'RESET'):
                    o_efek("Tahan...", "reset game")
                    t_start = time.ticks_ms()
                    is_reset_triggered = False
                    while not btn_reset.value():
                        if time.ticks_diff(time.ticks_ms(), t_start) > 3000:
                            o_efek("RESET GAME", "")
                            beep(600, 200)
                            time.sleep(1)
                            reset_game()
                            is_reset_triggered = True
                            break
                        time.sleep_ms(50)
                    if not is_reset_triggered:
                        o_state()
                elif key in ['A', 'B', 'C', 'D']:
                    if state["fase"] == "jawab" and not is_quotes:
                        is_multi = len(soal_aktif.get("jawaban_benar", "")) > 1
                        if is_multi:
                            if key in jawaban_terpilih:
                                jawaban_terpilih.remove(key)
                            else:
                                jawaban_terpilih.add(key)
                            beep(800, 50)
                            o_soal_opsi(soal_aktif["soal"], jawaban_terpilih)
                        else:
                            proses_jawaban(key)
        time.sleep_ms(50)

if __name__ == "__main__":
    main()
