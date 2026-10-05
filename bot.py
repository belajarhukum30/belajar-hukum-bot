import os
import json
import sqlite3
import random
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

DB = "quiz_stable.db"

# =========================
# BANK SOAL
# =========================
with open("questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

COURSES = sorted({str(q.get("course", "")).strip() for q in QUESTIONS if q.get("course")})


def clean_text(value):
    """Membersihkan typo OCR PDF tanpa mengubah substansi soal."""
    if value is None:
        return ""
    text = str(value)

    # Buang artefak header/footer dan nomor halaman yang ikut terbaca OCR.
    text = re.sub(r"\s*20005S62_ADPU4332.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*20005603_1SIP4131.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*HKUM420[129]\s*/\s*MODUL.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*ADPU4332\s*/\s*MODU[Ll]\s*\d+.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*Cocok[ck]a?n?l?a?h?.*$", "", text, flags=re.I)
    text = re.sub(r"\s*Cocokkanlah.*$", "", text, flags=re.I)
    text = re.sub(r"\s*Daftar Pustaka.*$", "", text, flags=re.I)

    # Koreksi OCR yang berulang pada PDF sumber.
    replacements = {
        "hukUJ11": "hukum", "hukUJ11": "hukum", "huku1n": "hukum",
        "Huku1n": "Hukum", "hukutn": "hukum", "huktn": "hukum",
        "hu.kum": "hukum", "Hukwn": "Hukum",
        "ad1ninistrasi": "administrasi", "Ad1ninistrasi": "Administrasi",
        "pen1erintah": "pemerintah", "Pen1erintah": "Pemerintah",
        "pen1erintahan": "pemerintahan", "pen1erintaban": "pemerintahan",
        "pe1nerintah": "pemerintah", "Pe1nerintah": "Pemerintah",
        "n1enjadi": "menjadi", "n1engatur": "mengatur",
        "n1erupakan": "merupakan", "n1empunyai": "mempunyai",
        "n1elakukan": "melakukan", "n1emberikan": "memberikan",
        "n1asyarakat": "masyarakat", "n1aksud": "maksud",
        "n1engenai": "mengenai", "n1engapa": "mengapa",
        "n1elalui": "melalui", "n1asing-masing": "masing-masing",
        "pe1nilihan": "pemilihan", "pe1ngadaan": "pengadaan",
        "pen1gadaan": "pengadaan", "per1aturan": "peraturan",
        "pe1rlindungan": "perlindungan", "se1nua": "semua",
        "sela1na": "selama", "dala1n": "dalam", "Dala1n": "Dalam",
        "a1tau": "atau", "A1tau": "Atau", "ba1wa": "bahwa",
        "Ba1wa": "Bahwa", "sa1npai": "sampai", "Sa1npai": "Sampai",
        "ter1nasuk": "termasuk", "ke1ompok": "kelompok",
        "ke1ompok": "kelompok", "kelo1npok": "kelompok",
        "pe1ayanan": "pelayanan", "pelaya11an": "pelayanan",
        "penyakit": "penyakit", "penyebaran": "penyebaran",
        "111elalui": "melalui", "111erupakan": "merupakan",
        "111empunyai": "mempunyai", "111elakukan": "melakukan",
        "1nenjadi": "menjadi", "1nengatur": "mengatur",
        "1nempunyai": "mempunyai", "1nelakukan": "melakukan",
        "1nemberikan": "memberikan", "1nasyarakat": "masyarakat",
        "1naksud": "maksud", "1nengenai": "mengenai", "1nelalui": "melalui",
        "1nasing-masing": "masing-masing",
        "se1nua": "semua", "se1lama": "selama", "per1nah": "pernah",
        "per1buatan": "perbuatan", "pe1mbagian": "pembagian",
        "pe1mbentukan": "pembentukan", "pe1merintah": "pemerintah",
        "pe1ngertian": "pengertian", "kepe1ntingan": "kepentingan",
        "me1nang": "memang", "da1lam": "dalam", "Da1lam": "Dalam",
        "Jern1an": "Jerman", "J ern1an": "Jerman",
        "Oppenhein1": "Oppenheim", "1-Iart": "Hart",
        "Beltefroid": "Bellefroid", "refom1asi": "reformasi",
        "sip ii": "sipil", "salab": "salah", "jav,aban": "jawaban",
        "javvaban": "jawaban", "se1nua": "semua", "kelo1npok": "kelompok",
        "rnenjadi": "menjadi", "rnelaksanakan": "melaksanakan",
        "rnelakukan": "melakukan", "rnerupakan": "merupakan",
        "rnenurut": "menurut", "rnasih": "masih", "rnernpunyai": "mempunyai",
        "rnernberikan": "memberikan", "rnasalah": "masalah",
        "rnelalui": "melalui", "rnernang": "memang",
        "n1": "m1",  # hanya sebagai tahap akhir untuk pola angka tertentu di bawah
    }

    # Jangan menjalankan mapping "n1" secara global karena dapat merusak
    # istilah lain. Hapus jika muncul sebagai efek samping.
    replacements.pop("n1", None)

    for old, new in replacements.items():
        text = text.replace(old, new)

    # ===== POLA TYPO OCR YANG SANGAT SERING MUNCUL =====
    # Beberapa huruf pada hasil OCR dapat berubah menjadi angka/huruf lain.
    # Koreksi dilakukan berdasarkan konteks kata agar tidak mengubah angka hukum.
    context_word_fixes = [
        (r"\bRak(?=\s+asasi\b)", "Hak"),
        (r"\bbak(?=\s+asasi\b)", "hak"),
        (r"\bRak(?=\s+alami\b)", "Hak"),
        (r"\bbak(?=\s+alami\b)", "hak"),
        (r"\btnanusia\b", "manusia"),
        (r"\btanusia\b", "manusia"),
        (r"\bmanusia\b", "manusia"),
        (r"\bp1tama\b", "pertama"),
        (r"\bpe1tama\b", "pertama"),
        (r"\bpe1ta1na\b", "pertama"),
        (r"\bgenerasi\s+pe1tama\b", "generasi pertama"),
        (r"\bgenerasi\s+p1tama\b", "generasi pertama"),
        (r"\bp1lihan\b", "pilihan"),
        (r"\bp1lihan\b", "pilihan"),
        (r"\bp1ngertian\b", "pengertian"),
        (r"\bp1raturan\b", "peraturan"),
        (r"\bp1rjanjian\b", "perjanjian"),
        (r"\bp1rlindungan\b", "perlindungan"),
        (r"\bp1merintah\b", "pemerintah"),
        (r"\bp1merintahan\b", "pemerintahan"),
        (r"\bp1layanan\b", "pelayanan"),
        (r"\bp1ndidikan\b", "pendidikan"),
        (r"\bp1ngawasan\b", "pengawasan"),
        (r"\bp1mbentukan\b", "pembentukan"),
        (r"\bp1mbagian\b", "pembagian"),
        (r"\bp1mberian\b", "pemberian"),
        (r"\bp1ngadaan\b", "pengadaan"),
        (r"\bp1nyelesaian\b", "penyelesaian"),
        (r"\bp1nyelenggaraan\b", "penyelenggaraan"),
        (r"\bp1nanganan\b", "penanganan"),
        (r"\bp1nangkatan\b", "pengangkatan"),
        (r"\bp1njelasan\b", "penjelasan"),
        (r"\bp1nyataan\b", "pernyataan"),
        (r"\bp1nyandang\b", "penyandang"),
        (r"\bp1nyalahgunaan\b", "penyalahgunaan"),
        (r"\bp1ngusaha\b", "pengusaha"),
        (r"\bp1kerja\b", "pekerja"),
        (r"\bp1kerjaan\b", "pekerjaan"),
        (r"\bp1menuhan\b", "pemenuhan"),
        (r"\bp1milu\b", "pemilu"),
        (r"\bp1laksanaan\b", "pelaksanaan"),
        (r"\bp1mbatasan\b", "pembatasan"),
        (r"\bp1mbelaan\b", "pembelaan"),
        (r"\bp1mbagian\b", "pembagian"),
        (r"\bp1ngaturan\b", "pengaturan"),
        (r"\bp1rjanjian\b", "perjanjian"),
        (r"\bp1rtanggungjawaban\b", "pertanggungjawaban"),
        (r"\bp1nduduk\b", "penduduk"),
        (r"\bp1nghormatan\b", "penghormatan"),
        (r"\bp1ngakuan\b", "pengakuan"),
        (r"\bp1lindungan\b", "perlindungan"),
        (r"\bp1ngadilan\b", "pengadilan"),
        (r"\bp1ngawasan\b", "pengawasan"),
        (r"\bp1ngetahuan\b", "pengetahuan"),
    ]
    for pat, repl in context_word_fixes:
        text = re.sub(pat, repl, text, flags=re.I)

    # Bentuk OCR lain yang sering muncul di modul sumber.
    more_word_fixes = {
        "dalarn": "dalam", "Dalarn": "Dalam", "dalar n": "dalam",
        "rnanusia": "manusia", "Rnanusia": "Manusia",
        "tnanusia": "manusia", "Tnanusia": "Manusia",
        "tern1asuk": "termasuk", "ter1nasuk": "termasuk",
        "mernberikan": "memberikan", "mernperoleh": "memperoleh",
        "rnerupakan": "merupakan", "rnenurut": "menurut",
        "rnenjadi": "menjadi", "rnenjelaskan": "menjelaskan",
        "rnelakukan": "melakukan", "rnelalui": "melalui",
        "rnasuk": "masuk", "rnasih": "masih", "rnasalah": "masalah",
        "rnernenuhi": "memenuhi", "rnernperhatikan": "memperhatikan",
        "rnernpunyai": "mempunyai", "rnenyatakan": "menyatakan",
        "rnenentukan": "menentukan", "rnenyusun": "menyusun",
        "rnernang": "memang", "rnernperoleh": "memperoleh",
        "hakt asasi": "hak asasi", "hak asasi tnanusia": "hak asasi manusia",
        "n1anusia": "manusia", "1nanusia": "manusia",
        "n1emiliki": "memiliki", "1nemiliki": "memiliki",
        "n1erupakan": "merupakan", "1nerupakan": "merupakan",
        "n1engandung": "mengandung", "1nengandung": "mengandung",
        "n1enghormati": "menghormati", "1nenghormati": "menghormati",
        "n1elindungi": "melindungi", "1nelindungi": "melindungi",
        "n1elekat": "melekat", "1nelekat": "melekat",
        "n1artabat": "martabat", "1nartabat": "martabat",
        "n1erampas": "merampas", "1nerampas": "merampas",
        "n1elanggar": "melanggar", "1nelanggar": "melanggar",
        "n1engapa": "mengapa", "1nengapa": "mengapa",
        "n1emberikan": "memberikan", "1nemberikan": "memberikan",
        "n1enurut": "menurut", "1nenurut": "menurut",
    }
    for old, new in more_word_fixes.items():
        text = text.replace(old, new)

    # Koreksi angka/huruf yang sangat khas OCR pada nomor UU/pasal/tahun.
    text = re.sub(r"\b20\s*l\s*l\b", "2011", text, flags=re.I)
    text = re.sub(r"\b20\s*l\s*0\b", "2010", text, flags=re.I)
    text = re.sub(r"\bNo1nor\b", "Nomor", text, flags=re.I)
    text = re.sub(r"\bNo1nor\b", "Nomor", text, flags=re.I)
    text = re.sub(r"\bTabun\b", "Tahun", text, flags=re.I)
    text = re.sub(r"\bTa1un\b", "Tahun", text, flags=re.I)
    text = re.sub(r"\bI\s*0\b", "10", text)
    text = re.sub(r"\bl\s*0\b", "10", text)
    text = re.sub(r"\b11/c\b", "II/c", text)

    # Buang sisa nomor halaman yang tertanam di tengah pilihan.
    text = re.sub(r"\s+\d+\s+Indroharto,.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s+\d+\s+20005S62.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*20005S62.*?(?=$|\n)", " ", text, flags=re.I)

    # ===== NORMALISASI OCR YANG LEBIH AGRESIF, TETAPI TERBATAS =====
    # Pola berikut sangat sering muncul pada hasil OCR buku/modul hukum.
    # "1n" dan "n1" -> "m" hanya ketika berada di dalam kata atau pada awal kata.
    # Angka murni tidak disentuh.
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])1n(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])1n(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])n1(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])n1(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<!\d)111(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])111(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    # OCR sering membaca awalan "m" sebagai "rn".
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])rn(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])rnen", "men", text, flags=re.I)
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])rner", "mer", text, flags=re.I)
    text = re.sub(r"(?<![A-Za-zÀ-ÖØ-öø-ÿ])rnas", "mas", text, flags=re.I)

    # OCR angka/huruf yang sangat khas pada awal/akhir kata.
    text = re.sub(r"\bl1ukum\b", "hukum", text, flags=re.I)
    text = re.sub(r"\bhuku111\b", "hukum", text, flags=re.I)
    text = re.sub(r"\bhukt1m\b", "hukum", text, flags=re.I)
    text = re.sub(r"\bhak(i|i1)m\b", "hakim", text, flags=re.I)

    # Beberapa bentuk OCR yang jelas dari kata Indonesia.
    extra_wordfix = {
        "rlierarki": "hierarki",
        "KUI-I": "KUH",
        "KUI-I": "KUH",
        "timtrr": "timur",
        "pemisaban": "pemisahan",
        "kedauJatan": "kedaulatan",
        "te1jadi": "terjadi",
        "te1nasuk": "termasuk",
        "me1nperhatikan": "memperhatikan",
        "me1nenuhi": "memenuhi",
        "me1nperoleh": "memperoleh",
        "me1mpunyai": "mempunyai",
        "men1pakan": "merupakan",
        "kepe1ntingan": "kepentingan",
        "pe1janjian": "perjanjian",
        "pe1nerintahan": "pemerintahan",
        "pe1nerintah": "pemerintah",
        "pen1erintahan": "pemerintahan",
        "pen1erintah": "pemerintah",
        "pe1nberian": "pemberian",
        "pe1nempatan": "penempatan",
        "pe1mbagian": "pembagian",
        "pe1mbentukan": "pembentukan",
        "pe1ngertian": "pengertian",
        "pe1ngadaan": "pengadaan",
        "pe1nilihan": "pemilihan",
        "pe1rlindungan": "perlindungan",
        "pe1nberdayaan": "pemberdayaan",
        "kelo1npok": "kelompok",
        "ke1ompok": "kelompok",
        "se1nua": "semua",
        "sela1na": "selama",
        "dala1n": "dalam",
        "da1lam": "dalam",
        "a1tau": "atau",
        "ba1wa": "bahwa",
        "sa1npai": "sampai",
        "u1num": "umum",
        "umu1n": "umum",
        "u1num": "umum",
        "siste1n": "sistem",
        "sisten1": "sistem",
        "sisteln": "sistem",
        "sistenm": "sistem",
        "1sjstem": "sistem",
        "n1asyarakat": "masyarakat",
        "1nasyarakat": "masyarakat",
        "n1enurut": "menurut",
        "1nenurut": "menurut",
        "n1enjadi": "menjadi",
        "1nenjadi": "menjadi",
        "n1engatur": "mengatur",
        "1nengatur": "mengatur",
        "n1erupakan": "merupakan",
        "1nerupakan": "merupakan",
        "n1empunyai": "mempunyai",
        "1nempunyai": "mempunyai",
        "n1elakukan": "melakukan",
        "1nelakukan": "melakukan",
        "n1emberikan": "memberikan",
        "1nemberikan": "memberikan",
        "n1engenai": "mengenai",
        "1nengenai": "mengenai",
        "n1elalui": "melalui",
        "1nelalui": "melalui",
        "n1aksud": "maksud",
        "1naksud": "maksud",
        "n1ateri": "materi",
        "1nateri": "materi",
        "n1anusia": "manusia",
        "1nanusia": "manusia",
        "n1asa": "masa",
        "1nasa": "masa",
        "n1ilik": "milik",
        "1nilik": "milik",
        "n1aka": "maka",
        "1naka": "maka",
        "n1aupun": "maupun",
        "1naupun": "maupun",
        "n1asing-masing": "masing-masing",
        "1nasing-masing": "masing-masing",
        "n1emenuhi": "memenuhi",
        "1nemenuhi": "memenuhi",
        "n1emperoleh": "memperoleh",
        "1nemperoleh": "memperoleh",
        "n1emperhatikan": "memperhatikan",
        "1nemperhatikan": "memperhatikan",
        "n1elaksanakan": "melaksanakan",
        "1nelaksanakan": "melaksanakan",
        "n1engharuskan": "mengharuskan",
        "1nengharuskan": "mengharuskan",
        "n1enyatakan": "menyatakan",
        "1nenyatakan": "menyatakan",
        "n1enyusun": "menyusun",
        "1nenyusun": "menyusun",
        "n1emiliki": "memiliki",
        "1nemiliki": "memiliki",
        "n1engandung": "mengandung",
        "1nengandung": "mengandung",
        "n1erupakan": "merupakan",
        "rnenjadi": "menjadi",
        "rnenurut": "menurut",
        "rnerupakan": "merupakan",
        "rnasih": "masih",
        "rnasalah": "masalah",
        "rnelalui": "melalui",
        "rnelakukan": "melakukan",
        "rnernberikan": "memberikan",
        "rnenyatakan": "menyatakan",
        "rnenjelaskan": "menjelaskan",
        "rnenentukan": "menentukan",
        "rnenyusun": "menyusun",
        "rnenurut": "menurut",
        "rnernpunyai": "mempunyai",
        "rnernpunyai": "mempunyai",
        "jabatamya": "jabatannya",
        "jabata1mya": "jabatannya",
        "metniliki": "memiliki",
        "me1niliki": "memiliki",
        "me1npunyai": "mempunyai",
        "fundan1ental": "fundamental",
        "len1baga": "lembaga",
        "le1nbaga": "lembaga",
        "kepen,ilikan": "kepemilikan",
        "kepen,ilikan": "kepemilikan",
        "pen,erintah": "pemerintah",
        "pen,erintahan": "pemerintahan",
        "pen,erima": "penerima",
        "tnata": "mata",
        "tnasing-masing": "masing-masing",
        "bak-hak": "hak-hak",
        "hukun1": "hukum",
        "hukun,": "hukum",
        "hukUJ11": "hukum",
        "hukutn": "hukum",
        "hukt1m": "hukum",
        "huktn": "hukum",
        "Hukwn": "Hukum",
        "ad1ninistrasi": "administrasi",
        "Ad1ninistrasi": "Administrasi",
        "Non1or": "Nomor",
        "No1nor": "Nomor",
        "Tabun": "Tahun",
        "Ta1un": "Tahun",
        "salab": "salah",
        "jav,aban": "jawaban",
        "javvaban": "jawaban",
        "altematif": "alternatif",
        "disiplin pegawai negeri sip ii": "disiplin pegawai negeri sipil",
        "penundaa11": "penundaan",
        "perb11atan": "perbuatan",
        "peme1intah": "pemerintah",
        "n1elanggar": "melanggar",
        "me1nbuktikan": "membuktikan",
        "n1e1nenuhi": "memenuhi",
        "n1e1nberikan": "memberikan",
        "n1e1npekerjakan": "mempekerjakan",
        "n1e1njadi": "menjadi",
        "n1e1n": "mem",
        "semuajawaban": "semua jawaban",
        "jawabanA,B,C": "jawaban A, B, dan C",
        "jawaban A,B,C": "jawaban A, B, dan C",
        "jawabanA,B,Csalah": "jawaban A, B, dan C salah",
        "sen1uanya": "semuanya",
        "the.fixed": "the fixed",
        "parlia1nenlaty": "parliamentary",
        "syste,n": "system",
        "govern1nent": "government",
        "p1·": "pr",
        "ke-beranekaan": "keberanekaan",
    }
    for old, new in extra_wordfix.items():
        text = text.replace(old, new)

    # OCR PDF sering membaca huruf "m" sebagai "n1" atau "111".
    # Terapkan hanya pada pola yang berada di dalam kata, agar angka 111
    # yang memang merupakan angka tidak ikut berubah.
    text = re.sub(r"n1e1n", "mem", text, flags=re.I)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])n1(?=[a-zA-ZÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<!\d)111(?=[a-zA-ZÀ-ÖØ-öø-ÿ])", "m", text)
    text = re.sub(r"(?<=[a-zA-ZÀ-ÖØ-öø-ÿ])111(?=[a-zA-ZÀ-ÖØ-öø-ÿ])", "m", text)

    # Beberapa bentuk OCR yang muncul berulang di bank soal.
    wordfix = {
        "n1e1npekerjakan": "mempekerjakan",
        "n1e1nberikan": "memberikan",
        "n1e1nberlakukan": "memberlakukan",
        "n1e1nberikan": "memberikan",
        "n1e1njadi": "menjadi",
        "n1enjadi": "menjadi",
        "n1engatur": "mengatur",
        "n1erupakan": "merupakan",
        "n1empunyai": "mempunyai",
        "n1elakukan": "melakukan",
        "n1emberikan": "memberikan",
        "n1engenai": "mengenai",
        "n1elalui": "melalui",
        "n1asyarakat": "masyarakat",
        "n1asing-masing": "masing-masing",
        "pen1erintah": "pemerintah",
        "Pen1erintah": "Pemerintah",
        "pen1erintahan": "pemerintahan",
        "pen1erintaban": "pemerintahan",
        "pe1nberdayaan": "pemberdayaan",
        "pe1nilihan": "pemilihan",
        "pe1ngadaan": "pengadaan",
        "pe1rlindungan": "perlindungan",
        "per1aturan": "peraturan",
        "ke1ompok": "kelompok",
        "kelo1npok": "kelompok",
        "dala1n": "dalam",
        "Dala1n": "Dalam",
        "se1nua": "semua",
        "ter1nasuk": "termasuk",
        "pe1nberian": "pemberian",
        "pe1nempatan": "penempatan",
        "pe1njelasan": "penjelasan",
        "pe1mbagian": "pembagian",
        "pe1mbentukan": "pembentukan",
        "kepe1ntingan": "kepentingan",
        "rnerupakan": "merupakan",
        "rnenjadi": "menjadi",
        "rnelakukan": "melakukan",
        "rnernberikan": "memberikan",
        "rnasalah": "masalah",
        "rnasih": "masih",
        "rnenurut": "menurut",
    }
    for old, new in wordfix.items():
        text = text.replace(old, new)

    text = text.replace("¬", "").replace("￾", "").replace("�", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\.{2,}", "…", text)
    # Koreksi gabungan kata yang berulang pada hasil OCR.
    concatfix = {
        "konsepnegara": "konsep negara",
        "Konsepnegara": "Konsep negara",
        "Konijnbeltmempunyai": "Konijnbelt mempunyai",
        "Konijnbelt didukung": "Konijnbelt didukung",
        "barangdanjasa": "barang dan jasa",
        "peraturanperundang-undangan": "peraturan perundang-undangan",
        "undang-undanglainnya": "undang-undang lainnya",
        "jawabanyang": "jawaban yang",
        "semuajawaban": "semua jawaban",
        "ciri-ciri": "ciri-ciri",
        "moden1": "modern",
        "moden": "modern",
        "yairu": "yaitu",
        "pe1janjian": "perjanjian",
        "pen,erintah": "pemerintah",
        "pen,erintahan": "pemerintahan",
    }
    for old, new in concatfix.items():
        text = text.replace(old, new)

    # Rapikan kata yang terpecah oleh OCR dan tanda baca yang nyasar.
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ]),(?=[A-Za-zÀ-ÖØ-öø-ÿ])", "", text)
    text = re.sub(r"(?<=[a-zà-ÿ])\.(?=[a-zà-ÿ])", "", text)
    text = re.sub(r"(?<=[A-Za-zÀ-ÖØ-öø-ÿ])\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\b([A-Za-zÀ-ÖØ-öø-ÿ]+)\s+([a-zà-ÿ]{1,3})\b", r"\1 \2", text)
    return text.strip()


def get_item(idx):
    """Validasi soal sebelum dipakai supaya 1 soal rusak tidak mematikan kuis."""
    if not isinstance(idx, int) or idx < 0 or idx >= len(QUESTIONS):
        raise ValueError("ID soal tidak valid")

    raw = QUESTIONS[idx]
    options = raw.get("options", [])
    if not isinstance(options, list):
        raise ValueError("Pilihan jawaban bukan list")
    options = [clean_text(x) for x in options if clean_text(x)]

    if len(options) < 2:
        raise ValueError("Soal memiliki kurang dari 2 pilihan")

    try:
        answer = int(raw.get("answer", -1))
    except Exception:
        raise ValueError("Kunci jawaban bukan angka")

    if answer < 0 or answer >= len(options):
        raise ValueError(f"Kunci jawaban di luar pilihan: {answer}")

    return {
        "course": clean_text(raw.get("course", "")),
        "module": clean_text(raw.get("module", "")),
        "test": clean_text(raw.get("test", "")),
        "q": clean_text(raw.get("q", "")),
        "options": options,
        "answer": answer,
        "explain": clean_text(raw.get("explain", "")),
        "key": clean_text(raw.get("key", "")),
    }


def _is_substantive_explanation(explain):
    """Mendeteksi apakah penjelasan bank soal benar-benar mengajar konsep."""
    if not explain:
        return False
    low = explain.lower()
    generic_markers = [
        "berasal dari tes formatif pada materi sumber",
        "jika belum yakin, ulangi kegiatan belajar",
        "cocokkan jawaban anda dengan kunci jawaban",
        "pelajari kembali materi",
        "pahami kembali konsep yang diuji",
        "jawaban yang benar adalah",
        "pilihan tersebut paling sesuai dengan",
    ]
    if any(m in low for m in generic_markers):
        return False
    # Penjelasan yang hanya mengulang pilihan juga belum cukup substantif.
    compact = re.sub(r"\s+", " ", low).strip(" .")
    return len(compact) >= 60 and not compact.startswith("soal ini berasal")


def _topic_phrase(q):
    q = clean_text(q).strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"^(menurut|berdasarkan)\s+.*?,\s*", "", q, flags=re.I)
    q = re.sub(r"^(apakah|manakah|yang manakah|apa yang dimaksud dengan)\s+", "", q, flags=re.I)
    q = re.sub(r"\b(adalah|merupakan|ialah)\s+.*$", "", q, flags=re.I)
    return q.strip(" .?…")


def build_explanation(item):
    """Pembahasan substantif: menjelaskan konsep dan alasan opsi benar.

    Urutan sumber:
    1) pembahasan asli bank soal jika memang substantif;
    2) pola khusus yang cocok dengan materi sumber;
    3) penjelasan konseptual dari hubungan pertanyaan-jawaban.
    """
    explain = clean_text(item.get("explain", "")).strip()
    answer = item["answer"]
    letter = chr(65 + answer)
    option = clean_text(item["options"][answer]).strip()
    q = clean_text(item.get("q", "")).strip()
    low = q.lower()
    opt_low = option.lower()

    if _is_substantive_explanation(explain):
        return explain

    # ===== POLA KHUSUS YANG TERDAPAT LANGSUNG DALAM MODUL SUMBER =====
    if "pengangkatan anak" in low and "memutuskan hubungan hukum" in low and "plena" in opt_low:
        return (
            "Adopsi Plena (Adoptio Plena): pengangkatan anak secara sempurna/penuh "
            "yang bertujuan memutuskan hubungan hukum dengan orang tua biologis. "
            "Karena soal menekankan adanya pemutusan hubungan hukum tersebut, "
            "istilah yang tepat adalah adopsi plena. Berbeda dengan adopsi minus plena, "
            "hubungan hukum dengan orang tua biologis tidak diputus sehingga hak waris "
            "anak terhadap orang tua biologis tetap ada."
        )

    if "generasi pertama" in low and ("politik dan sipil" in opt_low or "tuntutan untuk melepaskan diri" in opt_low):
        return (
            "Hak asasi manusia generasi pertama: berfokus pada hak sipil dan politik "
            "serta kebebasan individu. Generasi ini lahir dari tuntutan untuk melepaskan "
            "diri dari absolutisme negara dan melindungi kehidupan pribadi serta otonomi "
            "individu. Karena itu, pilihan yang menunjuk pada hak sipil-politik atau "
            "kebebasan dari absolutisme sesuai dengan ciri generasi pertama."
        )

    if "dianggap universal" in low and ("kemanusiaan setiap orang" in opt_low or "termasuk dalam kemanusiaan" in opt_low):
        return (
            "HAM bersifat universal: hak tersebut melekat pada setiap manusia hanya "
            "karena ia manusia. Universal berarti hak itu berlaku tanpa membedakan ras, "
            "jenis kelamin, bahasa, budaya, kewarganegaraan, agama, atau latar belakang "
            "lain. Jadi, pilihan yang menyatakan bahwa HAM termasuk dalam kemanusiaan "
            "setiap orang adalah tepat."
        )

    if ("melekat" in low or "inheren" in low) and "sejak lahir" in opt_low:
        return (
            "HAM yang melekat (inheren): hak tersebut sudah ada pada diri seseorang "
            "sejak lahir karena martabatnya sebagai manusia. Hak itu bukan hadiah dari "
            "negara, masyarakat, atau organisasi kekuasaan. Karena itu, pilihan yang "
            "menyebut melekat pada setiap orang sejak lahir menjelaskan makna "
            "‘melekat’ secara tepat."
        )

    if "pandangan islam" in low and "anugerah" in opt_low:
        return (
            "Pandangan Islam terhadap HAM: dalam materi sumber, Islam digambarkan "
            "menghormati hak asasi manusia dan memandangnya sebagai anugerah Tuhan. "
            "Karena itu, pilihan tersebut tepat: HAM dipandang sebagai sesuatu yang "
            "harus dihormati, bukan hak yang hanya berlaku bagi kelompok tertentu."
        )

    if "hubungan antara pancasila" in low and "hak asasi manusia" in low and "mencakup prinsip" in opt_low:
        return (
            "Pancasila dan HAM: hubungan keduanya bersifat mendukung, karena Pancasila "
            "memuat nilai dan prinsip yang berkaitan dengan penghormatan terhadap hak "
            "asasi manusia. Jadi, Pancasila bukan sesuatu yang bertentangan dengan HAM "
            "atau tidak berhubungan dengannya; pilihan yang menyatakan bahwa Pancasila "
            "mencakup prinsip-prinsip HAM adalah yang sesuai dengan materi."
        )

    if "uud 1945" in low and "universal declaration" in low:
        return (
            "UUD 1945 pada awalnya belum memuat banyak ketentuan HAM: materi sumber "
            "mengaitkannya dengan waktu penyusunan UUD 1945 yang mendahului Universal "
            "Declaration of Human Rights (UDHR) 1948. Karena itu, pilihan yang menekankan "
            "bahwa UUD 1945 disusun sebelum adanya UDHR menjadi alasan yang sesuai dengan "
            "pembahasan sumber."
        )

    if "universal declaration of human rights" in low and ("1948" in opt_low or "diterima" in low):
        return (
            "Universal Declaration of Human Rights (UDHR): deklarasi ini diterima "
            "pada tahun 1948 dan menjadi tonggak penting dalam perkembangan perlindungan "
            "HAM secara internasional. Karena itu, jika soal meminta tahunnya, angka 1948 "
            "adalah penentu jawaban."
        )

    if "pasal 28" in low and "pp nomor 43 tahun 1998" in low and "100 orang" in opt_low:
        return (
            "Ketentuan Pasal 28 PP Nomor 43 Tahun 1998: pengusaha wajib mempekerjakan "
            "sekurang-kurangnya 1 orang penyandang cacat yang memenuhi persyaratan "
            "jabatan dan kualifikasi pekerjaan untuk setiap 100 orang pekerja. Jadi, "
            "jawaban benar karena memuat tiga unsur penting sekaligus: jumlah minimal "
            "1 orang, batas setiap 100 pekerja, dan syarat jabatan/kualifikasi pekerjaan."
        )

    # ===== SOAL DEFINISI / PENGERTIAN =====
    if re.search(r"\bpengertian\b|\bdefinisi\b|\byang dimaksud\b|\bdiartikan\b|\bmaksud dari\b", low):
        topic = _topic_phrase(q) or "konsep yang ditanyakan"
        return (
            f"**{topic}:** jawaban {letter} tepat karena pilihan tersebut memuat "
            f"unsur yang menjadi inti pengertian {topic.lower()}. Dalam soal definisi, "
            "yang harus dicari adalah ciri yang membentuk konsep, bukan sekadar kata "
            "yang mirip. Jadi, pilihan ini benar karena menjelaskan substansi konsep "
            f"yang sedang diminta: {option}."
        )

    # ===== SOAL TOKOH / TEORI =====
    if re.search(r"\bmenurut\b|\bpendapat\b|\bdikemukakan oleh\b|\bdiperkenalkan oleh\b|\bteori .* oleh\b|\bmenafsirkan\b", low):
        return (
            f"Inti pendapat: {option}. Jawaban {letter} benar karena pilihan ini "
            "memasangkan tokoh/teori dengan gagasan yang sedang diuji. Kuncinya adalah "
            "mengingat isi gagasannya, bukan hanya nama tokohnya; pernyataan pada "
            f"pilihan {letter} menunjukkan substansi pendapat yang ditanyakan."
        )

    # ===== SOAL DASAR HUKUM / KETENTUAN =====
    if re.search(r"\bdasar hukum\b|\bdiatur dalam\b|\bdiatur oleh\b|\bketentuan\b|\bpasal\b|\buu nomor\b|\bperaturan pemerintah\b|\bperaturan presiden\b", low):
        return (
            f"Dasar/ketentuan yang tepat: {option}. Jawaban {letter} benar karena "
            "soal meminta aturan yang secara langsung mengatur objek yang dibahas. "
            "Dengan demikian, penentunya bukan sekadar nama peraturan yang terdengar "
            "berkaitan, tetapi kecocokan antara objek yang diatur dan isi ketentuannya."
        )

    # ===== SOAL KECUALI / TIDAK TERMASUK =====
    if re.search(r"\bkecuali\b|\btidak termasuk\b|\bbukan\b|\btidak merupakan\b", low):
        return (
            f"Jawaban {letter} benar karena kata kunci soal adalah ‘kecuali/tidak termasuk’. "
            "Artinya, yang dicari bukan anggota kelompok yang benar, melainkan satu "
            "pilihan yang tidak sesuai dengan kelompok tersebut. Pilihan ini tepat karena "
            f"{option} merupakan pengecualian yang diminta soal."
        )

    # ===== SOAL ANGKA / WAKTU =====
    if re.search(r"\bberapa\b|\bjumlah\b|\bsetiap\b|\bselama\b|\bjangka waktu\b|\bjangka\b|\bhari\b|\bbulan\b|\btahun\b|\bpersen\b|\b%\b", low):
        return (
            f"Nilai yang ditentukan soal: {option}. Jawaban {letter} benar karena "
            "ketentuan yang ditanyakan bergantung pada angka, jumlah, atau jangka waktu "
            "tertentu. Nilai pada pilihan ini sesuai dengan kondisi yang diminta, sehingga "
            "mengubah angkanya akan mengubah makna ketentuannya."
        )

    # ===== SOAL CIRI / UNSUR / KARAKTERISTIK =====
    if re.search(r"\bciri\b|\bkarakteristik\b|\bunsur\b|\bsifat\b|\bterdiri dari\b|\bmeliputi\b|\bkomponen\b", low):
        return (
            f"Ciri/unsur yang diuji: {option}. Jawaban {letter} benar karena "
            "pernyataan tersebut merupakan bagian yang membentuk atau mencirikan "
            "konsep yang ditanyakan. Jadi, yang dicocokkan adalah hubungan antara "
            "unsur tersebut dan konsepnya, bukan sekadar kemiripan kata."
        )

    # ===== SOAL SEBAB / TUJUAN / FUNGSI =====
    if re.search(r"\bmengapa\b|\bsebab\b|\btujuan\b|\bfungsi\b|\buntuk apa\b|\bmanfaat\b", low):
        return (
            f"Alasan/fungsi: {option}. Jawaban {letter} benar karena pilihan ini "
            "menjelaskan hubungan sebab, tujuan, atau fungsi yang diminta oleh soal. "
            "Dengan kata lain, pilihan tersebut menjawab ‘mengapa’ atau ‘untuk apa’ "
            "konsep itu ada dalam konteks materi."
        )

    # ===== SOAL PERBANDINGAN =====
    if re.search(r"\bperbedaan\b|\bberbeda\b|\bperbandingan\b|\bsedangkan\b|\bsementara\b", low):
        return (
            f"Pembeda utama: {option}. Jawaban {letter} benar karena pilihan ini "
            "menunjukkan sisi yang membedakan konsep-konsep yang dibandingkan. Pada "
            "soal perbandingan, pernyataan yang benar secara umum belum tentu menjadi "
            "jawaban; yang dicari adalah ciri yang benar-benar menjadi pembeda."
        )

    # ===== SEMUA JAWABAN =====
    if "semua jawaban" in opt_low and "benar" in opt_low:
        return (
            "Pilihan ini benar apabila seluruh pernyataan yang dirangkum di dalamnya "
            "sesuai dengan konsep yang ditanyakan dan tidak ada yang bertentangan. "
            "Jadi, ‘semua jawaban benar’ merupakan kesimpulan setelah setiap pernyataan "
            "sebelumnya memenuhi unsur yang diminta soal."
        )

    # ===== FALLBACK YANG TETAP MENGAJAR =====
    topic = _topic_phrase(q) or "konsep yang ditanyakan"
    return (
        f"Inti konsep: {option}. Jawaban {letter} benar karena pilihan tersebut "
        f"menjelaskan hubungan yang tepat dengan {topic.lower()}. Cara memahaminya: "
        f"ketika soal menanyakan {topic.lower()}, pernyataan yang dipilih harus memuat "
        "unsur yang memang menjadi ciri, fungsi, akibat, atau hubungan hukum dari "
        f"konsep tersebut. Pada pilihan ini, unsur kuncinya adalah {option}, sehingga "
        "pilihan tersebut paling sesuai dengan pokok materi yang diuji."
    )


def _memory_core(text, max_words=12):
    """Memadatkan jawaban menjadi cue singkat/mind-map, bukan salinan jawaban."""
    text = clean_text(text).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[.]+$", "", text)

    # Frasa hukum penting dipadatkan terlebih dahulu agar tidak terpotong oleh
    # aturan penghapusan kata umum.
    phrase_fixes = [
        (r"\bsekurang-kurangnya\b", "min."),
        (r"\byang memenuhi persyaratan jabatan dan kualifikasi pekerjaan\b", "sesuai jabatan/kualifikasi"),
        (r"\bmerupakan delegasi kewenangan dari\b", "delegasi wewenang dari"),
        (r"\bdelegasi kewenangan dari\b", "delegasi wewenang dari"),
        (r"\bdari rakyat kepada pemerintah\b", "rakyat → pemerintah"),
        (r"\bkepada pemerintah\b", "→ pemerintah"),
        (r"^semua hal yang\s+", ""),
        (r"^hal yang\s+", ""),
        (r"\bdalam rangka\b", "untuk"),
        (r"\byang secara tegas diberikan oleh\b", "yang diberikan oleh"),
    ]
    for pat, repl in phrase_fixes:
        text = re.sub(pat, repl, text, flags=re.I)

    # Ubah penghubung panjang menjadi simbol agar cue mudah dipanggil kembali.
    text = re.sub(r"\s+merupakan\s+", " ", text, flags=re.I)
    text = re.sub(r"\s+dan\s+", " + ", text, flags=re.I)
    text = re.sub(r"\s+yang\s+", " ", text, flags=re.I)
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # Buang pembuka tata bahasa yang tidak membantu ingatan.
    text = re.sub(r"^(yaitu|adalah|merupakan|bahwa)\s+", "", text, flags=re.I)
    words = text.split()
    if len(words) <= max_words:
        return text

    # Pertahankan bagian sebelum koma/semicolon jika sudah cukup pendek.
    parts = re.split(r"[,;]", text, maxsplit=1)
    first = parts[0].strip()
    if len(first.split()) <= max_words:
        return first

    stop = {
        "yang", "dan", "atau", "dengan", "untuk", "dari", "kepada", "dalam",
        "pada", "oleh", "sebagai", "suatu", "seorang", "hal", "ini", "itu",
        "adalah", "merupakan", "bahwa", "serta", "akan", "dapat", "harus",
        "secara", "tidak", "lebih", "tersebut", "terhadap", "bagi", "agar",
    }
    kept = []
    for w in words:
        bare = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9/-]", "", w).lower()
        if bare in stop and len(kept) >= 3:
            continue
        kept.append(w)
        if len(kept) >= max_words:
            break
    return " ".join(kept)


def _memory_subject(question):
    q = clean_text(question).strip()
    # Tokoh: prioritaskan nama sebelum kata kerja seperti menafsirkan/menurut.
    m = re.match(r"(?:.*?)([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){1,3})\s+(?:menafsirkan|menurut|mengemukakan|menyatakan|berpendapat|mengartikan)\b", q)
    if m:
        return m.group(1).strip()

    # Pola pertanyaan definisi: ambil objek sebelum "adalah/merupakan".
    m = re.search(r"(?:pengertian|definisi)\s+(?:dari|tentang)?\s*([^,?…]+?)(?:\s+sebagai)?\s*(?:adalah|merupakan|ialah)\b", q, flags=re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" .")

    # Dasar hukum/ketentuan.
    m = re.search(r"(Pasal\s+\d+[^,?]*|UU\s+Nomor\s+[^,?]*)", q, flags=re.I)
    if m:
        return m.group(1).strip()

    # Untuk soal ciri/unsur/fungsi, ambil inti sesudah kata tanya.
    q = re.sub(r"^(berikut ini|yang dimaksud dengan|yang dimaksud|manakah|apakah)\s*", "", q, flags=re.I)
    q = re.sub(r"\s+(adalah|merupakan|ialah)\s+.*$", "", q, flags=re.I)
    return " ".join(q.split()[:7]).strip(" .?…")


def build_memory_key(item):
    """Kunci ingatan = cue pendek untuk memicu kembali jawaban, bukan salinan jawaban."""
    answer = item["answer"]
    option = item["options"][answer]
    question = item.get("q", "")
    subject = _memory_subject(question)
    core = _memory_core(option, max_words=12)

    # Format utama: pemicu → inti. Ini lebih mudah dipanggil kembali daripada
    # menampilkan seluruh kalimat jawaban.
    if subject:
        # Hindari pengulangan jika subject sudah menjadi bagian inti.
        if subject.lower() in core.lower():
            return f"{subject} → {core}"
        return f"{subject} → {core}"
    return f"{core}"

# =========================
# DATABASE
# =========================
def init_db():
    con = sqlite3.connect(DB)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                score INTEGER DEFAULT 0,
                answered INTEGER DEFAULT 0
            )
        """)

        user_cols = {r[1] for r in con.execute("PRAGMA table_info(users)").fetchall()}
        if "name" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN name TEXT")
        if "score" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 0")
        if "answered" not in user_cols:
            con.execute("ALTER TABLE users ADD COLUMN answered INTEGER DEFAULT 0")

        con.execute("""
            CREATE TABLE IF NOT EXISTS wrong (
                user_id INTEGER,
                question_id INTEGER,
                times_wrong INTEGER DEFAULT 1,
                PRIMARY KEY(user_id, question_id)
            )
        """)

        wrong_cols = {r[1] for r in con.execute("PRAGMA table_info(wrong)").fetchall()}
        if "times_wrong" not in wrong_cols:
            con.execute("ALTER TABLE wrong ADD COLUMN times_wrong INTEGER DEFAULT 1")

        con.commit()
    finally:
        con.close()


def save_user(user):
    con = sqlite3.connect(DB)
    try:
        con.execute(
            "INSERT OR IGNORE INTO users(user_id, name, score, answered) VALUES(?,?,0,0)",
            (user.id, user.full_name),
        )
        con.execute("UPDATE users SET name=? WHERE user_id=?", (user.full_name, user.id))
        con.commit()
    finally:
        con.close()


def record_answer(uid, qid, correct):
    # Pastikan user selalu ada, termasuk bila menekan tombol dari pesan lama.
    con = sqlite3.connect(DB)
    try:
        con.execute(
            "INSERT OR IGNORE INTO users(user_id, name, score, answered) VALUES(?,?,0,0)",
            (uid, "Pengguna"),
        )
        con.execute(
            "UPDATE users SET answered=COALESCE(answered,0)+1, score=COALESCE(score,0)+? WHERE user_id=?",
            (1 if correct else 0, uid),
        )
        if correct:
            con.execute("DELETE FROM wrong WHERE user_id=? AND question_id=?", (uid, qid))
        else:
            con.execute("""
                INSERT INTO wrong(user_id, question_id, times_wrong)
                VALUES(?,?,1)
                ON CONFLICT(user_id, question_id)
                DO UPDATE SET times_wrong=COALESCE(times_wrong,0)+1
            """, (uid, qid))
        con.commit()
    finally:
        con.close()


def stats(uid):
    con = sqlite3.connect(DB)
    try:
        row = con.execute("SELECT COALESCE(score,0), COALESCE(answered,0) FROM users WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            row = (0, 0)
        wrong = con.execute("SELECT COUNT(*) FROM wrong WHERE user_id=?", (uid,)).fetchone()[0]
        return row[0], row[1], wrong
    finally:
        con.close()


def wrong_ids(uid):
    con = sqlite3.connect(DB)
    try:
        return [r[0] for r in con.execute("SELECT question_id FROM wrong WHERE user_id=?", (uid,)).fetchall()]
    finally:
        con.close()


# =========================
# MENU
# =========================
def course_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(course, callback_data=f"course:{i}")]
        for i, course in enumerate(COURSES)
    ])


def module_keyboard(course):
    modules = sorted(
        {q.get("module", "") for q in QUESTIONS if q.get("course") == course},
        key=lambda x: int(x.split()[-1]) if x.split()[-1].isdigit() else 999,
    )
    rows = [[InlineKeyboardButton("📚 Semua modul", callback_data=f"module:{course}:all")]]
    rows += [[InlineKeyboardButton(m, callback_data=f"module:{course}:{m}")] for m in modules]
    rows += [[InlineKeyboardButton("⬅️ Mata kuliah", callback_data="back:courses")]]
    return InlineKeyboardMarkup(rows)


# =========================
# KIRIM SOAL
# =========================
async def send_question(chat_id, context, pool):
    if not pool:
        await context.bot.send_message(chat_id, "❌ Tidak ada soal pada pilihan ini.")
        return

    last = context.user_data.get("last_qid")
    choices = [x for x in pool if x != last] or list(pool)

    # Cari soal valid. Jika ada soal rusak, lewati soal itu saja.
    random.shuffle(choices)
    for idx in choices:
        try:
            item = get_item(idx)
            break
        except Exception as exc:
            print("SOAL DILEWATI:", idx, repr(exc))
    else:
        await context.bot.send_message(chat_id, "⚠️ Bank soal pada pilihan ini perlu diperbaiki.")
        return

    context.user_data["last_qid"] = idx
    context.user_data["current_qid"] = idx

    keyboard = [
        [InlineKeyboardButton(f"{chr(65+j)}. {option}", callback_data=f"ans:{idx}:{j}")]
        for j, option in enumerate(item["options"][:4])
    ]

    header = f"📚 {item['course']}\n📖 {item['module']}"
    if item["test"]:
        header += f"\n📝 {item['test']}"

    await context.bot.send_message(
        chat_id,
        f"{header}\n\n🧠 {item['q']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================
# COMMAND
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        "📚 BELAJAR HUKUM — KUIS\n\n"
        "Pilih mata kuliah, lalu modul. Setelah menjawab, pembahasan dan kunci ingatan akan muncul.\n\n"
        "/kuis — mulai kuis\n/skor — lihat skor\n/salah — ulangi soal yang pernah salah"
    )
    await update.message.reply_text("📖 Pilih mata kuliah:", reply_markup=course_keyboard())


async def kuis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text("📖 Pilih mata kuliah:", reply_markup=course_keyboard())


async def skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    score, answered, wrong = stats(update.effective_user.id)
    nilai = score / answered * 100 if answered else 0
    await update.message.reply_text(
        f"📊 SKOR BELAJAR\n\nBenar: {score}\nTotal dijawab: {answered}\nNilai: {nilai:.0f}%\n❌ Perlu diulang: {wrong}"
    )


async def salah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    ids = wrong_ids(update.effective_user.id)
    if not ids:
        await update.message.reply_text("🎉 Belum ada soal yang perlu diulang.")
        return
    context.user_data["mode"] = "wrong"
    context.user_data["pool"] = ids
    await send_question(update.effective_chat.id, context, ids)


# =========================
# CALLBACK MENU
# =========================
async def choose_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        index = int(query.data.split(":", 1)[1])
        course = COURSES[index]
        context.user_data["course"] = course
        await query.edit_message_text(f"📖 {course}\n\nPilih modul:", reply_markup=module_keyboard(course))
    except Exception as exc:
        print("ERROR COURSE:", repr(exc))
        await query.message.reply_text("⚠️ Menu mata kuliah bermasalah. Ketik /kuis lagi.")


async def choose_module(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        _, course, module = query.data.split(":", 2)
        ids = [
            i for i, q in enumerate(QUESTIONS)
            if q.get("course") == course and (module == "all" or q.get("module") == module)
        ]
        if not ids:
            await query.message.reply_text("❌ Belum ada soal pada pilihan ini.")
            return
        context.user_data["course"] = course
        context.user_data["module"] = module
        context.user_data["mode"] = "normal"
        context.user_data["pool"] = ids
        context.user_data["last_qid"] = None
        await query.message.reply_text(f"📖 {course} — {module}\n\n🧠 Berikut soalnya:")
        await send_question(query.message.chat_id, context, ids)
    except Exception as exc:
        print("ERROR MODULE:", repr(exc))
        await query.message.reply_text("⚠️ Modul tidak dapat dibuka. Ketik /kuis lagi.")


async def back_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📖 Pilih mata kuliah:", reply_markup=course_keyboard())


# =========================
# JAWABAN
# =========================
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Telegram memang mengharuskan callback query dijawab.
    await query.answer()

    try:
        parts = query.data.split(":")
        if len(parts) != 3:
            raise ValueError("Format tombol jawaban tidak valid")

        idx = int(parts[1])
        chosen = int(parts[2])
        item = get_item(idx)

        if chosen < 0 or chosen >= len(item["options"]):
            raise ValueError("Pilihan jawaban tidak valid")

        correct = chosen == item["answer"]
        record_answer(query.from_user.id, idx, correct)

        result = "✅ BENAR!" if correct else "❌ BELUM TEPAT"
        explanation = build_explanation(item)
        key = build_memory_key(item)

        # Kirim hasil sebagai pesan baru. Ini sengaja dibuat lebih aman daripada
        # mengedit pesan soal yang sudah diklik.
        text = (
            f"{result}\n\n"
            f"Jawaban benar:\n"
            f"{chr(65 + item['answer'])}. {item['options'][item['answer']]}\n\n"
            f"💡 PEMBAHASAN\n{explanation}\n\n"
            f"🔑 KUNCI INGATAN\n{key}\n\n"
            f"📌 SUMBER\n{item['course']} — {item['module']} — {item['test']}"
        )

        # Batas aman Telegram untuk pesan teks adalah 4096 karakter.
        if len(text) > 3900:
            text = text[:3900] + "\n\n[teks dipersingkat agar Telegram menerima pesan]"

        await query.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➡️ Soal berikutnya", callback_data="next")]
            ])
        )

        # Hilangkan tombol lama supaya tidak dijawab berkali-kali.
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass

    except Exception as exc:
        # Tulis error lengkap ke log FadeHost, bukan menyembunyikannya.
        print("ERROR ANSWER:", repr(exc))
        try:
            await query.message.reply_text(
                "⚠️ Terjadi kesalahan teknis saat memproses jawaban.\n"
                "Soal ini dilewati. Tekan /kuis untuk melanjutkan."
            )
        except Exception:
            pass


async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if context.user_data.get("mode") == "wrong":
        pool = wrong_ids(query.from_user.id)
        context.user_data["pool"] = pool
        if not pool:
            await query.message.reply_text("🎉 Semua soal yang sebelumnya salah sudah benar!")
            return
    else:
        pool = context.user_data.get("pool", [])

    await send_question(query.message.chat_id, context, pool)


async def error_handler(update, context):
    print("BOT ERROR:", repr(context.error))


def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN belum diatur di FadeHost.")

    init_db()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("kuis", kuis))
    app.add_handler(CommandHandler("skor", skor))
    app.add_handler(CommandHandler("salah", salah))
    app.add_handler(CallbackQueryHandler(choose_course, pattern=r"^course:\d+$"))
    app.add_handler(CallbackQueryHandler(choose_module, pattern=r"^module:"))
    app.add_handler(CallbackQueryHandler(back_courses, pattern=r"^back:courses$"))
    app.add_handler(CallbackQueryHandler(answer, pattern=r"^ans:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(next_question, pattern=r"^next$"))
    app.add_error_handler(error_handler)

    print(f"🤖 Belajar Hukum Bot berjalan. Bank soal: {len(QUESTIONS)} soal.")
    app.run_polling()


if __name__ == "__main__":
    main()
