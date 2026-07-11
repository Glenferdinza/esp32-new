# boot.py
import gc
import machine
import time
import sys

# Simpan referensi WLAN secara global di boot.py agar tidak di-garbage collect (GC)
wlan_ref = None

gc.collect()

try:
    import setup_wifi
    setup_wifi.connect_or_setup()
    
    # Kunci referensi wlan_sta agar tetap hidup di C-level SDK
    wlan_ref = setup_wifi.wlan_sta
    
    # Hapus modul setup_wifi secara total untuk membebaskan RAM
    if "setup_wifi" in sys.modules:
        del sys.modules["setup_wifi"]
        
    # Hapus variabel lokal
    try:
        del setup_wifi
    except:
        pass
        
    gc.collect()
except Exception as e:
    err_str = str(e)
    if "Memory" in err_str or "3001" in err_str or isinstance(e, MemoryError):
        print("[SYSTEM] WiFi OOM terdeteksi saat boot. Melakukan Hard Reset otomatis...")
        time.sleep(1)
        machine.deepsleep(100)
    else:
        raise e
