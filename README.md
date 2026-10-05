# Belajar Hukum — Telegram Quiz Bot (Versi Bank Soal Besar)

Bot Telegram untuk belajar 7 mata kuliah hukum.

## Isi
- Bank awal: 398 soal yang diekstrak dari bagian Tes Formatif pada 7 PDF kuliah yang diberikan.
- Pilih mata kuliah → modul → kuis.
- Pembahasan singkat dan sumber modul ditampilkan setelah jawaban.
- Skor pengguna tersimpan di SQLite.
- Soal yang salah dicatat dan dapat diulang dengan `/salah`.
- Tidak ada token Telegram di repository ini.

## Mata kuliah
1. Pengantar Ilmu Hukum
2. Hukum Administrasi Negara
3. Hukum Perdata
4. Hukum Tata Negara
5. Ilmu Negara
6. Pendidikan Kewarganegaraan
7. Sistem Hukum Indonesia

## Menjalankan
Set environment variable `BOT_TOKEN`, lalu:

```bash
pip install -r requirements.txt
python bot.py
```

## Catatan
Bank ini adalah versi pertama yang memprioritaskan soal Tes Formatif agar cepat dapat dipakai. Bank dapat diperbesar lagi dengan mengambil soal dari bagian Latihan dan mengembangkan soal turunan dari materi/rangkuman, dengan tetap menjaga agar isi bersumber dari PDF kuliah.
