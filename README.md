# Panduan Penggunaan dan Unggah Kode ESP32 Sangkara

Repositori ini berisi program permainan Sangkara yang disesuaikan untuk beberapa varian mikrokontroler ESP32 alternatif (varian tanpa layar OLED fisik dan varian Cheap Yellow Display).

## Apa itu Format MPY?

Secara default, MicroPython membaca file biner berformat kode sumber Python biasa (.py) dan menerjemahkannya ke dalam bytecode biner di dalam memori RAM mikrokontroler pada saat program pertama kali diimpor. Untuk program yang berukuran besar (seperti modul logika utama game Sangkara yang berukuran lebih dari 50 KB), proses penerjemahan teks ini membutuhkan alokasi memori dinamis yang sangat besar sehingga sering memicu kegagalan sistem berupa "MemoryError: memory allocation failed".

Format .mpy adalah file bytecode biner yang telah dikompilasi terlebih dahulu di komputer menggunakan tool mpy-cross. Dengan mengunggah file .mpy:
1. Mikrokontroler tidak perlu melakukan parsing teks kode sumber saat runtime.
2. Konsumsi memori RAM saat startup berkurang hingga lebih dari 50%.
3. Waktu booting dan import modul menjadi jauh lebih cepat.

Oleh karena itu, file logika utama (sangkara.mpy) dan file konfigurasi jaringan (setup_wifi.mpy) dikirim dalam bentuk bytecode, sedangkan file konfigurasi awal boot (boot.py) dan script pemanggil (main.py) tetap berformat .py biasa agar dapat dikenali langsung oleh interpreter MicroPython saat perangkat dinyalakan.

---

## Struktur Direktori

Proyek ini terbagi menjadi dua varian konfigurasi hardware:

### 1. sangkara_no_oled
Varian ini digunakan jika ESP32 Anda tidak dihubungkan ke layar OLED fisik.
*   boot.py: Script inisialisasi awal.
*   main.py: Script pemanggil modul utama game.
*   setup_wifi.mpy: Bytecode untuk portal konfigurasi jaringan Wi-Fi lokal.
*   sangkara.mpy: Bytecode logika game utama yang dialihkan output layarnya ke terminal konsol serial (MockOLED).

### 2. sangkara_cyd
Varian khusus untuk board Cheap Yellow Display (ESP32 dengan layar warna ILI9341 internal).
*   boot.py: Script inisialisasi awal.
*   main.py: Script pemanggil modul utama game.
*   setup_wifi.mpy: Bytecode konfigurasi Wi-Fi dengan alokasi pin buzzer pada GPIO 21.
*   sangkara.mpy: Bytecode game utama yang disesuaikan dengan konfigurasi pin RGB LED bawaan CYD (GPIO 4, 16, 17) serta stub interface layar LCD.

---

## Panduan Detail Unggah Menggunakan Thonny IDE

Berikut adalah langkah lengkap untuk mengunggah berkas program ke ESP32 menggunakan Thonny IDE:

### Langkah 1: Persiapan Koneksi Perangkat
1. Hubungkan board ESP32 ke port USB komputer menggunakan kabel data micro-USB atau USB-C yang berkualitas baik (pastikan kabel mendukung transfer data, bukan hanya pengisian daya).
2. Buka Device Manager di Windows Anda, lalu periksa pada bagian "Ports (COM & LPT)" untuk mengetahui nomor port serial yang aktif (misalnya COM3 atau COM4). Jika port tidak terdeteksi, Anda perlu menginstal driver USB-to-UART seperti driver Silicon Labs CP210x atau driver CH340 sesuai chip yang digunakan pada board Anda.

### Langkah 2: Konfigurasi Interpreter Thonny
1. Buka aplikasi Thonny IDE di komputer Anda.
2. Buka menu Tools -> Options pada bagian atas menu utama.
3. Pilih tab Interpreter pada jendela opsi yang muncul.
4. Pada pilihan menu dropdown pertama ("Which interpreter should Thonny use..."), ubah dan pilih MicroPython (ESP32).
5. Pada pilihan menu dropdown kedua ("Port"), pilih nomor port serial COM yang sesuai dengan perangkat ESP32 Anda (misalnya COM3 atau Silicon Labs CP210x USB to UART Bridge).
6. Klik tombol OK. Panel shell di bagian bawah Thonny akan terhubung ke perangkat dan menampilkan prompt command MicroPython seperti `>>>`.

### Langkah 3: Mengunggah Berkas ke ESP32
1. Aktifkan panel pengelola berkas di Thonny melalui menu utama View -> Files. Panel file akan muncul di sisi kiri jendela Thonny.
   *   Panel atas dinamakan "This computer" (berkas lokal di komputer Anda).
   *   Panel bawah dinamakan "MicroPython device" (penyimpanan flash di dalam board ESP32 Anda).
2. Pada panel atas ("This computer"), navigasikan folder ke lokasi proyek ini dan pilih salah satu folder varian yang ingin digunakan (misal folder `sangkara_no_oled` atau `sangkara_cyd`).
3. Blok atau pilih semua file yang berada di dalam folder tersebut:
   *   boot.py
   *   main.py
   *   setup_wifi.mpy
   *   sangkara.mpy
4. Klik kanan pada berkas yang telah diblok tersebut di panel atas, lalu pilih opsi Upload to /.
5. Proses pengunggahan akan berjalan. Pastikan status bar di bagian bawah selesai dan tidak menampilkan pesan error.

### Langkah 4: Menjalankan Program
1. Setelah semua berkas berhasil diunggah ke panel "MicroPython device", tekan tombol tombol merah Stop/Restart Backend di bagian atas panel menu Thonny, atau tekan tombol reset fisik (RST/EN) yang ada pada board ESP32 Anda.
2. Program akan langsung dijalankan secara otomatis saat startup. Output log jalannya game dapat dipantau secara langsung melalui panel Shell Thonny.
