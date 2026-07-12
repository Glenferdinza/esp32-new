import re
import os
import tokenize
import io
import sys

def minify(source_path, dest_path):
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Gunakan python tokenizer untuk mendeteksi semua komentar secara aman
    try:
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        comment_spans = []
        for toktype, tokval, start, end, line in tokens:
            if toktype == tokenize.COMMENT:
                comment_spans.append((start, end))
                
        lines = content.split('\n')
        # Hapus komentar dari baris (dari belakang agar index tidak bergeser)
        for start, end in reversed(comment_spans):
            l_idx = start[0] - 1
            col_start = start[1]
            lines[l_idx] = lines[l_idx][:col_start].rstrip()
    except Exception as e:
        print("Gagal menggunakan tokenizer, fallback ke regex:", e)
        lines = content.split('\n')

    clean_lines = []
    for line in lines:
        stripped = line.strip()
        # Lewati baris kosong
        if stripped == '':
            continue
        # Lewati jika hanya sisa baris komentar penuh
        if stripped.startswith('#'):
            continue
        clean_lines.append(line.rstrip())

    # Tulis hasil kompresi
    with open(dest_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(clean_lines))

def compile_mpy(py_path):
    try:
        import subprocess
        mpy_dest = py_path.replace('.py', '.mpy')
        subprocess.run(['py', '-m', 'mpy_cross', py_path], check=True)
        print(f"Kompilasi berhasil! Ukuran bytecode: {os.path.getsize(mpy_dest)} bytes")
        return True
    except Exception as e:
        print(f"Gagal mengompilasi {py_path} ke bytecode .mpy: {e}")
        return False

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Definisikan target folder
    folders = ['sangkara_cyd', 'sangkara_no_oled']
    processed = False
    
    for folder in folders:
        folder_path = os.path.join(base_dir, folder)
        if not os.path.exists(folder_path):
            continue
            
        # 1. Cek apakah ada file mentah developer (sangkara_esp32_api.py) di folder ini
        dev_file = os.path.join(folder_path, 'sangkara_esp32_api.py')
        target_py = os.path.join(folder_path, 'sangkara.py')
        
        if os.path.exists(dev_file):
            print(f"\n[+] Memproses minifikasi di folder {folder}...")
            minify(dev_file, target_py)
            print(f"Minifikasi selesai! Ukuran awal: {os.path.getsize(dev_file)} bytes, Ukuran hasil: {os.path.getsize(target_py)} bytes")
            compile_mpy(target_py)
            processed = True
        elif os.path.exists(target_py):
            # 2. Jika tidak ada file API mentah, cukup kompilasi sangkara.py yang ada ke .mpy
            print(f"\n[+] Mengompilasi sangkara.py di folder {folder}...")
            compile_mpy(target_py)
            processed = True

    if not processed:
        print("Tidak ada berkas sangkara.py atau sangkara_esp32_api.py yang ditemukan untuk diproses.")
