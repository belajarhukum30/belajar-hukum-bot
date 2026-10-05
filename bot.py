import os, random, sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise RuntimeError("BOT_TOKEN belum diisi.")
DB="quiz.db"
COURSES={
"pih":("Pengantar Ilmu Hukum",["Ruang Lingkup Pengantar Ilmu Hukum","Arti dan Definisi Hukum","Tujuan dan Fungsi Hukum","Norma Hukum dan Norma Sosial","Hukum Objektif dan Subjektif","Sumber-Sumber Hukum","Penggolongan Hukum","Mazhab Ilmu Pengetahuan Hukum","Pembentukan dan Pengisian Kekosongan Hukum"]),
"han":("Hukum Administrasi Negara",["Pengertian Hukum Administrasi Negara","Instrumen HAN","Aparatur Negara","Pengelolaan Barang Milik Negara","Perlindungan Hukum bagi Masyarakat","Hukum Pengelolaan Keuangan Negara","Hukum Keterbukaan Informasi Publik","Hukum Pelayanan Publik","Hukum Kesejahteraan Sosial"]),
"perdata":("Hukum Perdata",["Pengertian dan Ruang Lingkup Hukum Perdata","Hukum Orang/Pribadi","Badan Hukum dan Domisili","Hukum Keluarga dan Perkawinan","Putusnya Perkawinan, Perwalian dan Adopsi","Hukum Benda","Hukum Jaminan","Hukum Waris","Hukum Perikatan","Aneka Perjanjian"]),
"htn":("Hukum Tata Negara",["Pengertian Umum dan Sumber Hukum Tata Negara","Teori Konstitusi","Bentuk dan Susunan Negara serta Sistem Pemerintahan","Hak Asasi Manusia","Kewarganegaraan","Pemilihan Umum dan Partai Politik","Parlemen","Lembaga Kepresidenan","Kekuasaan Kehakiman"]),
"ilneg":("Ilmu Negara",["Konsep Ilmu Negara","Teori Asal Mula Negara","Klasifikasi Negara","Susunan Negara","Legitimasi Kekuasaan","Pembatasan Kekuasaan"]),
"pkn":("Pendidikan Kewarganegaraan",["Hakikat, Tujuan dan Dinamika Pendidikan Kewarganegaraan","Warga Negara, Kewarganegaraan dan Identitas Nasional","Demokrasi dan HAM","Negara, Konstitusi dan Penegakan Hukum","Integrasi Nasional dan Wawasan Nusantara","Globalisasi dan Ketahanan Nasional"]),
"shi":("Sistem Hukum Indonesia",["Pengertian Sistem Hukum Indonesia","Hukum Adat","Sistem Hukum Islam","Hukum Tata Negara Indonesia","Hukum Perdata","Hukum Administrasi Negara","Hukum Pidana","Hukum Acara","Hukum Internasional"]),}
Q=[
("pih",1,"Menurut materi, apa tiga kelompok ilmu hukum?",["Ilmu tentang kaidah, ilmu pengertian, dan ilmu tentang kenyataan","Pidana, perdata, tata negara","Tertulis, tidak tertulis, adat","Publik, privat, acara"],0,"Materi menyebut tiga kelompok: ilmu tentang kaidah, ilmu pengertian, dan ilmu tentang kenyataan.","🧠 Kaidah — Pengertian — Kenyataan."),
("pih",1,"Apa fungsi utama Pengantar Ilmu Hukum?",["Memberikan dasar untuk memahami ilmu hukum","Menggantikan semua mata kuliah hukum","Membahas hanya hukum pidana","Membahas hanya putusan"],0,"PIH memberi dasar untuk memahami ilmu hukum dan hukum positif.","🧠 PIH = fondasi belajar hukum."),
("han",9,"Manakah yang termasuk sarana/prasarana penyelenggaraan kesejahteraan sosial?",["Panti sosial","Bursa efek","Pelabuhan","Kantor pos"],0,"Materi menyebut panti sosial sebagai salah satu sarana/prasarana kesejahteraan sosial.","🧠 Kesejahteraan sosial → panti, rehabilitasi, pendidikan/pelatihan."),
("perdata",1,"Menurut sistematika KUHPerdata, Buku III mengatur tentang...",["Perikatan","Orang","Benda","Pembuktian dan daluwarsa"],0,"Materi menyebut Buku I Orang, Buku II Benda, Buku III Perikatan, Buku IV Pembuktian dan Daluwarsa.","🧠 I Orang — II Benda — III Perikatan — IV Pembuktian/Daluwarsa."),
("perdata",10,"Salah satu syarat sah perjanjian menurut Pasal 1320 KUHPerdata adalah...",["Kesepakatan","Keturunan","Kewarganegaraan","Domisili hakim"],0,"Materi menyebut sepakat, kecakapan, hal tertentu, dan sebab yang halal.","🧠 Sepakat — Cakap — Hal tertentu — Sebab halal."),
("htn",9,"Menurut materi, kekuasaan kehakiman merupakan kekuasaan yang...",["Independen dan imparsial","Selalu di bawah legislatif","Selalu di bawah eksekutif","Tidak terkait konstitusi"],0,"Materi menjelaskan kekuasaan kehakiman sebagai kekuasaan yang independen dan imparsial.","🧠 Yudisial = mandiri + imparsial."),
("htn",9,"Di Indonesia, kekuasaan kehakiman dilaksanakan oleh...",["Mahkamah Agung dan Mahkamah Konstitusi","DPR dan DPD","Presiden dan DPR","BPK dan KPK"],0,"Materi menjelaskan kekuasaan kehakiman dilaksanakan oleh MA dan MK.","🧠 MA + MK."),
("ilneg",1,"Apa yang dibahas dalam Modul 1 Ilmu Negara?",["Konsep Ilmu Negara","Perjanjian jual beli","Hukum acara pidana","Hukum waris"],0,"Modul 1 membahas istilah, objek, ruang lingkup Ilmu Negara dan hubungannya dengan ilmu politik, HTN, dan hukum konstitusi.","🧠 Modul 1 = konsep dasar Ilmu Negara."),
("ilneg",6,"Apa dua hal utama yang dibahas dalam Modul 6 Ilmu Negara?",["Pembagian kekuasaan dan checks and balances","Perkawinan dan waris","Sumber hukum materiil dan formil","Pemilu dan partai politik"],0,"Modul 6 membahas pembagian kekuasaan dan mekanisme checks and balances.","🧠 Batasi kekuasaan = bagi + saling mengimbangi."),
("pkn",1,"Salah satu tujuan Pendidikan Kewarganegaraan adalah membentuk individu yang memiliki...",["Kesadaran dan tanggung jawab terhadap negara dan masyarakat","Kemampuan hanya dalam ekonomi","Kekuasaan atas lembaga negara","Kewenangan membuat UU"],0,"Materi menjelaskan tujuan PKn antara lain membentuk kesadaran dan tanggung jawab terhadap negara dan masyarakat sesuai nilai Pancasila dan UUD 1945.","🧠 PKn = sadar + bertanggung jawab sebagai warga negara."),
("pkn",1,"Manakah yang termasuk materi pokok Pendidikan Kewarganegaraan?",["Identitas nasional","Hanya hukum pidana","Hanya hukum perdata","Hanya hukum internasional"],0,"Materi pokok mencakup identitas nasional, integrasi nasional, konstitusi, hak dan kewajiban, demokrasi, penegakan hukum, wawasan nusantara, dan ketahanan nasional.","🧠 PKn menghubungkan warga negara, negara, konstitusi, demokrasi, dan kebangsaan."),
("shi",1,"Menurut materi, Sistem Hukum Indonesia disusun oleh berapa sub-sistem besar?",["Empat","Dua","Enam","Sepuluh"],0,"Materi menyebut empat sub-sistem besar: Hukum Adat, Hukum Islam, Hukum Barat, dan Hukum Nasional.","🧠 Adat — Islam — Barat — Nasional."),
("shi",1,"Menurut materi, Sistem Hukum Indonesia adalah...",["Semua sistem hukum yang diberlakukan berdasarkan politik hukum NKRI dan diakui berlaku di Indonesia","Hanya hukum nasional setelah kemerdekaan","Hanya hukum adat","Hanya hukum kolonial"],0,"Materi memberi pengertian yang mencakup sistem hukum yang diberlakukan berdasarkan politik hukum NKRI dan diakui berlaku di Indonesia.","🧠 Sistem Hukum Indonesia lebih luas daripada satu sumber hukum saja."),]

def db():
 c=sqlite3.connect(DB); c.execute("CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY,score INTEGER DEFAULT 0,answered INTEGER DEFAULT 0)"); c.execute("CREATE TABLE IF NOT EXISTS wrong(user_id INTEGER,q_index INTEGER,PRIMARY KEY(user_id,q_index))"); c.commit(); return c

def home(): return InlineKeyboardMarkup([[InlineKeyboardButton(v[0],callback_data=f"c:{k}")] for k,v in COURSES.items()])
def modules(k): return InlineKeyboardMarkup([[InlineKeyboardButton(f"Modul {i+1} — {m}",callback_data=f"m:{k}:{i+1}")] for i,m in enumerate(COURSES[k][1])] + [[InlineKeyboardButton("⬅️ Kembali",callback_data="home")]])
def pick(k,n):
 a=[i for i,x in enumerate(Q) if x[0]==k and x[1]==n] or [i for i,x in enumerate(Q) if x[0]==k]
 return random.choice(a) if a else None

async def start(u:Update,ctx:ContextTypes.DEFAULT_TYPE): await u.message.reply_text("📚 *Belajar Hukum*\n\nPilih mata kuliah:",parse_mode="Markdown",reply_markup=home())
async def skor(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
 r=db().execute("SELECT score,answered FROM users WHERE user_id=?",(u.effective_user.id,)).fetchone() or (0,0)
 await u.message.reply_text(f"📊 *Skor kamu*\n\nBenar: {r[0]}\nDijawab: {r[1]}",parse_mode="Markdown")
async def cb(u:Update,ctx:ContextTypes.DEFAULT_TYPE):
 q=u.callback_query; await q.answer(); d=q.data
 if d=="home": await q.edit_message_text("📚 Pilih mata kuliah:",reply_markup=home()); return
 if d.startswith("c:"):
  k=d[2:]; await q.edit_message_text(f"📖 *{COURSES[k][0]}*\n\nPilih modul:",parse_mode="Markdown",reply_markup=modules(k)); return
 if d.startswith("m:"):
  _,k,n=d.split(":"); idx=pick(k,int(n))
  if idx is None: await q.edit_message_text("Soal untuk mata kuliah ini belum dimasukkan.",reply_markup=modules(k)); return
  x=Q[idx]; keys=[[InlineKeyboardButton(f"{chr(65+i)}. {a}",callback_data=f"a:{idx}:{i}")] for i,a in enumerate(x[3])]
  await q.edit_message_text(f"❓ *Soal*\n\n{x[2]}",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(keys)); return
 if d.startswith("a:"):
  _,si,ai=d.split(":"); idx,ans=int(si),int(ai); x=Q[idx]; c=db(); c.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)",(u.effective_user.id,)); c.execute("UPDATE users SET answered=answered+1 WHERE user_id=?",(u.effective_user.id,))
  if ans==x[4]: c.execute("UPDATE users SET score=score+1 WHERE user_id=?",(u.effective_user.id,)); out="✅ *Benar!*"
  else: c.execute("INSERT OR IGNORE INTO wrong VALUES(?,?)",(u.effective_user.id,idx)); out=f"❌ *Belum tepat.*\nJawaban: *{chr(65+x[4])}. {x[3][x[4]]}*"
  c.commit(); await q.edit_message_text(f"{out}\n\n💡 *Penjelasan*\n{x[5]}\n\n{x[6]}",parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Soal berikutnya",callback_data=f"m:{x[0]}:{x[1]}")],[InlineKeyboardButton("📚 Pilih mata kuliah",callback_data="home")]]))

def main():
 db().close(); app=Application.builder().token(TOKEN).build(); app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("skor",skor)); app.add_handler(CallbackQueryHandler(cb)); app.run_polling()
if __name__=="__main__": main()
