import os
import json
import sqlite3
import random
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

DB = "quiz.db"

# =========================
# BANK SOAL
# =========================
with open("questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

COURSES = sorted({str(q.get("course", "")).strip() for q in QUESTIONS if q.get("course")})


def clean_text(value):
    if value is None:
        return ""
    text = str(value)

    # Artefak nomor halaman / header PDF yang ikut terbaca OCR
    text = re.sub(r"\s*20005S62_ADPU4332.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*20005603_1SIP4131.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*HKUM4201\s*/\s*MODUL.*?(?=$|\n)", " ", text, flags=re.I)
    text = re.sub(r"\s*Cocok[ck]a?n?l?a?h?\s+jawaban.*$", "", text, flags=re.I)
    text = re.sub(r"\s*Cocokkanlah.*$", "", text, flags=re.I)
    text = re.sub(r"\s*Daftar Pustaka.*$", "", text, flags=re.I)

    replacements = {
        "huku1n": "hukum", "Huku1n": "Hukum", "hu.kum": "hukum",
        "pen1erintah": "pemerintah", "Pen1erintah": "Pemerintah",
        "ad1ninistrasi": "administrasi", "Ad1ninistrasi": "Administrasi",
        "pe1nerintah": "pemerintah", "Pe1nerintah": "Pemerintah",
        "n1enjadi": "menjadi", "n1engatur": "mengatur", "n1erupakan": "merupakan",
        "n1empunyai": "mempunyai", "n1elakukan": "melakukan", "n1emberikan": "memberikan",
        "n1asyarakat": "masyarakat", "n1aksud": "maksud", "n1engenai": "mengenai",
        "n1engapa": "mengapa", "n1elalui": "melalui", "n1asing-masing": "masing-masing",
        "pe1nilihan": "pemilihan", "pe1ngadaan": "pengadaan", "pen1gadaan": "pengadaan",
        "per1aturan": "peraturan", "pe1rlindungan": "perlindungan", "se1nua": "semua",
        "sela1na": "selama", "dala1n": "dalam",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("¬", "").replace("￾", "").replace("�", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
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
        explanation = item["explain"] or "Pembahasan belum tersedia pada bank soal."
        key = item["key"] or "Kunci ingatan belum tersedia pada bank soal."

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
                "⚠️ Soal ini bermasalah dan sudah saya lewati.\n"
                "Tekan /kuis untuk melanjutkan."
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
