import network
wlan_sta = network.WLAN(network.STA_IF)
wlan_sta.active(True)
try:
    wlan_sta.config(pm=0) # Disable power save mode to prevent ETIMEDOUT packet drops
except:
    pass
wlan_ap  = network.WLAN(network.AP_IF)

import time, json, machine, _thread
import usocket as socket
from machine import Pin, PWM

KELOMPOK_ID = 1

# CYD default buzzer is Pin 21
try:
    buzzer = Pin(21, Pin.OUT)
except:
    buzzer = None

def o_header(t1, t2=""):
    print("[CYD-LCD-HEADER]", t1, "|", t2)

def beep(freq, duration):
    if buzzer:
        try:
            # Software bit-banged duty-cycled beep to prevent brownouts
            half_period = int(500000 / freq)
            period = half_period * 2
            pulse_high = min(int(period * 0.1), 30)
            pulse_low = period - pulse_high
            cycles = int((duration * 1000) / period)
            for _ in range(cycles):
                buzzer.value(1)
                time.sleep_us(pulse_high)
                buzzer.value(0)
                time.sleep_us(pulse_low)
        except:
            pass

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

dns_active = True
def dns_thread_func():
    global dns_active
    print("[DNS] Thread started")
    udps = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udps.settimeout(1.0)
    try:
        udps.bind(('0.0.0.0', 53))
        print("[DNS] Server bound to port 53 successfully")
    except Exception as e:
        print("[DNS] Bind error:", e)
        return
    while dns_active:
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
            continue
        except Exception as e:
            print("[DNS] Query parse error:", e)
    try:
        udps.close()
    except Exception as e:
        print("[DNS] Socket close error:", e)

def start():
    try:
        wlan_sta.disconnect()
        wlan_sta.active(False)
    except:
        pass

    time.sleep(1)

    try:
        wlan_ap.active(True)
        time.sleep_ms(500)
        wlan_ap.config(essid="SANGKARA-KLP" + str(KELOMPOK_ID), authmode=0)
    except Exception as e:
        print("AP init error, retrying...", e)
        time.sleep(1)
        wlan_ap.active(True)
        time.sleep_ms(500)
        wlan_ap.config(essid="SANGKARA-KLP" + str(KELOMPOK_ID), authmode=0)

    global dns_active
    dns_active = True
    try:
        _thread.start_new_thread(dns_thread_func, ())
    except Exception as e:
        print("Failed to start DNS thread:", e)
    
    o_header("WiFi Config", "Buka 192.168.4.1")
    print("[AP] SSID: SANGKARA-KLP" + str(KELOMPOK_ID))
    
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80))
    s.listen(1)
    s.settimeout(0.5)
    failed_attempts = {}
    
    while True:
        try:
            conn, addr = s.accept()
            conn.settimeout(1.0)
        except OSError:
            continue
        except:
            time.sleep_ms(100)
            continue
            
        try:
            req = conn.recv(1024)
            req_str = req.decode('utf-8', 'ignore')
            if req_str:
                print("[HTTP] Request from", addr, ":", req_str.split("\n")[0].strip())
        except OSError:
            try:
                conn.close()
            except:
                pass
            continue
        except Exception as e:
            print("Request read error:", e)
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
                conn.send(b'HTTP/1.1 302 Found\r\nLocation: http://192.168.4.1/\r\nConnection: close\r\n\r\n')
            except:
                pass
            try:
                conn.close()
            except:
                pass
            continue
            
        def send_html(html_body):
            try:
                conn.send(b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n')
                conn.send(b'<html><head><meta name="viewport" content="width=device-width, initial-scale=1">')
                conn.send(b'<style>*{box-sizing:border-box;}body{font-family:sans-serif;background:#f0f2f5;margin:0;padding:20px;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:90vh;}.container{background:white;padding:30px;border-radius:12px;box-shadow:0 8px 24px rgba(30,58,95,0.08);width:100%;max-width:360px;text-align:center;}h1{color:#1E3A5F;font-size:28px;margin:0 0 20px 0;}h3{color:#333;margin:0 0 15px 0;font-size:18px;}input{width:100%;padding:12px;margin:10px 0;border:1px solid #ccc;border-radius:6px;font-size:16px;outline:none;}input:focus{border-color:#1E3A5F;}button{width:100%;padding:12px;color:white;border:none;border-radius:6px;font-weight:bold;font-size:16px;cursor:pointer;margin-top:10px;background:#1E3A5F;}</style></head>')
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
                send_html('<h3>Akses Ditangguhkan</h3><p style="color:#666;font-size:14px;margin:10px 0 20px 0;">Anda telah salah memasukkan sandi sebanyak 3 kali. Akses dinonaktifkan sementara.</p>')
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
                        <span style="position:absolute;right:10px;top:50%;transform:translateY(-50%);cursor:pointer;display:flex;align-items:center;user-select:none;" onclick="togglePass(\'wifi_pass\',this)"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#666" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg></span>
                    </div>
                    <button type="submit">Hubungkan</button>
                    </form>''')
                else:
                    failed_attempts[client_ip] = failed_attempts.get(client_ip, 0) + 1
                    send_html('<h3>Login Admin</h3><p style="color:red;font-size:14px;">Kata sandi salah!</p><form method="POST" action="/login"><input type="password" name="admin_pass" placeholder="Password Admin" required><button type="submit">Login</button></form>')
            
            elif "POST /save " in req_str:
                parts = req_str.split("\r\n\r\n")
                if len(parts) < 2:
                    parts = req_str.split("\n\n")
                body = parts[-1] if len(parts) >= 2 else ""
                
                ssid = ""
                password = ""
                for pair in body.split("&"):
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        if k == "ssid":
                            ssid = unquote(v)
                        elif k == "password":
                            password = unquote(v)
                
                if ssid:
                    send_html('''<div style="text-align:center;">
                    <div style="font-size:54px;color:#22c55e;margin-bottom:16px;font-weight:bold;">✓</div>
                    <h3 style="color:#1e3a8a;margin-bottom:8px;font-size:20px;">WiFi Berhasil Disimpan!</h3>
                    <p style="color:#475569;font-size:14px;line-height:20px;margin-bottom:20px;">
                        Alat sedang memulai ulang (reboot) untuk terhubung ke WiFi:<br>
                        <b style="color:#1e3a8a;font-size:15px;">''' + ssid + '''</b>.<br><br>
                        Silakan sambungkan kembali HP/laptop Anda ke WiFi <b>Sangkara-Net</b>.
                    </p>
                    <div style="font-size:11px;color:#94a3b8;font-style:italic;">Halaman ini dapat ditutup sekarang.</div>
                    </div>''')
                    save_wifi_config(ssid, password)
                    dns_active = False
                    try:
                        s.close()
                    except:
                        pass
                    o_header("WiFi Disimpan", "Rebooting...")
                    beep(800, 500)
                    time.sleep(3)
                    machine.reset()
                else:
                    send_html('<h3>Gagal</h3><p style="color:red;font-size:14px;">SSID tidak boleh kosong!</p><a href="/"><button>Kembali</button></a>')
            
            else:
                send_html('<h3>Login Admin</h3><form method="POST" action="/login"><input type="password" name="admin_pass" placeholder="Password Admin" required><button type="submit">Login</button></form>')
                
        except Exception as e:
            print("Client handler error:", e)
            try:
                conn.close()
            except:
                pass

def connect_or_setup():
    cfg = None
    try:
        with open("wifi_config.json", "r") as f:
            cfg = json.loads(f.read())
    except:
        pass

    if cfg:
        ssid = cfg.get("ssid", "")
        pwd = cfg.get("password", "")
        print("Membaca konfigurasi WiFi dari wifi_config.json...")
        print("SSID:", ssid)
        
        print("[WIFI] Melakukan hard reset driver WiFi...")
        try:
            wlan_sta.active(False)
            wlan_ap.active(False)
        except:
            pass
        time.sleep(1.5)
        
        wlan_sta.active(True)
        time.sleep(1.0)
        
        wlan_sta.connect(ssid, pwd)
        
        o_header("SANGKARA", "Konek WiFi...")
        t = 150
        while not wlan_sta.isconnected() and t > 0:
            time.sleep_ms(100)
            t -= 1
            
        if wlan_sta.isconnected():
            print("WiFi Terhubung! IP Address:", wlan_sta.ifconfig()[0])
            o_header("WiFi OK", wlan_sta.ifconfig()[0])
            time.sleep(1)
            try:
                wlan_ap.active(False)
            except:
                pass
            
            global buzzer
            buzzer = None
            import gc
            gc.collect()
            return True
            
        print("WiFi Gagal terhubung.")
        o_header("WiFi Gagal!", "Buka Portal...")
        time.sleep(2)
        
    start()
    return False
