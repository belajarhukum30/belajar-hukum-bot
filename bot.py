import os
import json
import sqlite3
import random
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


DB = "quiz.db"


# =========================================================
# LOAD BANK SOAL
# =========================================================

with open("questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

COURSES = sorted({q["course"] for q in QUESTIONS})


# =========================================================
# MEMBERSIHKAN TEKS OCR
# =========================================================

def clean_text(value):
    """Membersihkan hasil OCR PDF sebelum ditampilkan di Telegram."""

    if value is None:
        return ""

    text = str(value)

    # Buang nomor/keterangan halaman PDF yang ikut masuk ke soal/pilihan.
    text = re.sub(
        r"\s*20005S62_ADPU4332.*?(?=$|\n)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*20005603_1SIP4131.*?(?=$|\n)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*HKUM4201\s*/\s*MODUL.*?(?=$|\n)",
        " ",
        text,
        flags=re.IGNORECASE,
    )

    # Buang teks petunjuk/akhir tes yang kadang ikut masuk pilihan.
    text = re.sub(
        r"\s*Cocok[ck]a?n?l?a?h?\s+jawaban.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*Cocokkanlah.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*Daftar Pustaka.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Perbaikan OCR yang sering muncul pada PDF kuliah.
    replacements = {
        "huku1n": "hukum",
        "Huku1n": "Hukum",
        "hu.kum": "hukum",
        "pen1erintah": "pemerintah",
        "Pen1erintah": "Pemerintah",
        "ad1ninistrasi": "administrasi",
        "Ad1ninistrasi": "Administrasi",
        "pe1nerintah": "pemerintah",
        "Pe1nerintah": "Pemerintah",
        "n1enjadi": "menjadi",
        "n1engatur": "mengatur",
        "n1erupakan": "merupakan",
        "n1empunyai": "mempunyai",
        "n1elakukan": "melakukan",
        "n1emberikan": "memberikan",
        "n1asyarakat": "masyarakat",
        "n1aksud": "maksud",
        "n1engenai": "mengenai",
        "n1engapa": "mengapa",
        "n1elalui": "melalui",
        "n1asing-masing": "masing-masing",
        "pe1nilihan": "pemilihan",
        "pe1ngadaan": "pengadaan",
        "pen1gadaan": "pengadaan",
        "per1aturan": "peraturan",
        "pe1rlindungan": "perlindungan",
        "se1nua": "semua",
        "sela1na": "selama",
        "dala1n": "dalam",
        "dapat di1n": "dapat dim",
        "111": "111",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    # Hilangkan artefak OCR yang jelas.
    text = text.replace("¬", "")
    text = text.replace("￾", "")
    text = text.replace("�", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)

    # Rapikan spasi sebelum tanda baca.
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)

    return text.strip()


def cleaned_item(item):
    """Membuat salinan soal yang sudah dibersihkan."""
    return {
        "course": clean_text(item.get("course", "")),
        "module": clean_text(item.get("module", "")),
        "test": clean_text(item.get("test", "")),
        "q": clean_text(item.get("q", "")),
        "options": [clean_text(x) for x in item.get("options", [])],
        "answer": int(item.get("answer", 0)),
        "explain": clean_text(item.get("explain", "")),
        "key": clean_text(item.get("key", "")),
    }


# =========================================================
# DATABASE
# =========================================================

def init_db():
    con = sqlite3.connect(DB)

    con.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            score INTEGER DEFAULT 0,
            answered INTEGER DEFAULT 0
        )
    """)

    # Database lama mungkin belum mempunyai kolom name/score/answered.
    columns = [
        row[1]
        for row in con.execute("PRAGMA table_info(users)").fetchall()
    ]

    if "name" not in columns:
        con.execute("ALTER TABLE users ADD COLUMN name TEXT")

    if "score" not in columns:
        con.execute(
            "ALTER TABLE users ADD COLUMN score INTEGER DEFAULT 0"
        )

    if "answered" not in columns:
        con.execute(
            "ALTER TABLE users ADD COLUMN answered INTEGER DEFAULT 0"
        )

    con.execute("""
        CREATE TABLE IF NOT EXISTS wrong (
            user_id INTEGER,
            question_id INTEGER,
            times_wrong INTEGER DEFAULT 1,
            PRIMARY KEY(user_id, question_id)
        )
    """)

    con.commit()
    con.close()


def save_user(user):
    con = sqlite3.connect(DB)

    con.execute(
        "INSERT OR IGNORE INTO users(user_id, name) VALUES(?, ?)",
        (user.id, user.full_name),
    )

    con.execute(
        "UPDATE users SET name=? WHERE user_id=?",
        (user.full_name, user.id),
    )

    con.commit()
    con.close()


def record_answer(uid, qid, correct):
    con = sqlite3.connect(DB)

    con.execute(
        """
        UPDATE users
        SET answered = answered + 1,
            score = score + ?
        WHERE user_id = ?
        """,
        (1 if correct else 0, uid),
    )

    if correct:
        con.execute(
            """
            DELETE FROM wrong
            WHERE user_id=? AND question_id=?
            """,
            (uid, qid),
        )
    else:
        con.execute(
            """
            INSERT INTO wrong(user_id, question_id, times_wrong)
            VALUES(?,?,1)
            ON CONFLICT(user_id, question_id)
            DO UPDATE SET times_wrong=times_wrong+1
            """,
            (uid, qid),
        )

    con.commit()
    con.close()


def stats(uid):
    con = sqlite3.connect(DB)

    row = con.execute(
        """
        SELECT score, answered
        FROM users
        WHERE user_id=?
        """,
        (uid,),
    ).fetchone()

    if row is None:
        row = (0, 0)

    wrong = con.execute(
        """
        SELECT COUNT(*)
        FROM wrong
        WHERE user_id=?
        """,
        (uid,),
    ).fetchone()[0]

    con.close()

    return row[0], row[1], wrong


# =========================================================
# MENU
# =========================================================

def course_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    course,
                    callback_data=f"course:{i}",
                )
            ]
            for i, course in enumerate(COURSES)
        ]
    )


def module_keyboard(course):
    modules = sorted(
        {
            q["module"]
            for q in QUESTIONS
            if q["course"] == course
        },
        key=lambda x: (
            int(x.split()[-1])
            if x.split()[-1].isdigit()
            else 999
        ),
    )

    rows = [
        [
            InlineKeyboardButton(
                "📚 Semua modul",
                callback_data=f"module:{course}:all",
            )
        ]
    ]

    rows += [
        [
            InlineKeyboardButton(
                module,
                callback_data=f"module:{course}:{module}",
            )
        ]
        for module in modules
    ]

    rows += [
        [
            InlineKeyboardButton(
                "⬅️ Mata kuliah",
                callback_data="back:courses",
            )
        ]
    ]

    return InlineKeyboardMarkup(rows)


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    await update.message.reply_text(
        "📚 BELAJAR HUKUM — KUIS\n\n"
        "Pilih mata kuliah, kemudian pilih modul.\n"
        "Setelah menjawab, pembahasan dan kunci ingatan akan langsung muncul.\n\n"
        "/kuis — mulai kuis\n"
        "/skor — lihat skor\n"
        "/salah — ulangi soal yang pernah salah"
    )

    await update.message.reply_text(
        "📖 Pilih mata kuliah:",
        reply_markup=course_keyboard(),
    )


async def kuis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    await update.message.reply_text(
        "📖 Pilih mata kuliah:",
        reply_markup=course_keyboard(),
    )


async def skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    score, answered, wrong = stats(
        update.effective_user.id
    )

    percentage = (
        score / answered * 100
        if answered
        else 0
    )

    await update.message.reply_text(
        f"📊 SKOR BELAJAR\n\n"
        f"Benar: {score}\n"
        f"Total dijawab: {answered}\n"
        f"Nilai: {percentage:.0f}%\n"
        f"❌ Soal yang masih perlu diulang: {wrong}"
    )


async def salah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)

    uid = update.effective_user.id

    con = sqlite3.connect(DB)
    rows = con.execute(
        """
        SELECT question_id
        FROM wrong
        WHERE user_id=?
        """,
        (uid,),
    ).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text(
            "🎉 Belum ada soal yang perlu diulang."
        )
        return

    context.user_data["mode"] = "wrong"

    await send_question(
        update.effective_chat.id,
        context,
        uid,
        [row[0] for row in rows],
    )


# =========================================================
# CALLBACK MENU
# =========================================================

async def choose_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    index = int(query.data.split(":")[1])
    course = COURSES[index]

    context.user_data["course"] = course

    await query.edit_message_text(
        f"📖 {course}\n\nPilih modul:",
        reply_markup=module_keyboard(course),
    )


async def choose_module(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, course, module = query.data.split(":", 2)

    context.user_data["course"] = course
    context.user_data["module"] = module
    context.user_data["mode"] = "normal"

    ids = [
        i
        for i, question in enumerate(QUESTIONS)
        if question["course"] == course
        and (
            module == "all"
            or question["module"] == module
        )
    ]

    if not ids:
        await query.edit_message_text(
            "❌ Belum ada soal pada pilihan ini."
        )
        return

    context.user_data["pool"] = ids
    context.user_data["last_qid"] = None

    # Hapus menu modul lama supaya tampilan tidak bertumpuk.
    try:
        await query.edit_message_text(
            f"📖 {course} — {module}\n\n"
            "🧠 Berikut soalnya:",
        )
    except Exception:
        pass

    await send_question(
        query.message.chat_id,
        context,
        query.from_user.id,
        ids,
    )


async def back_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "📖 Pilih mata kuliah:",
        reply_markup=course_keyboard(),
    )


# =========================================================
# SOAL
# =========================================================

async def send_question(chat_id, context, uid, pool=None):
    if pool is None:
        pool = context.user_data.get("pool")

    if not pool:
        await context.bot.send_message(
            chat_id,
            "❌ Belum ada bank soal untuk pilihan ini.",
        )
        return

    last = context.user_data.get("last_qid")

    choices = [
        qid for qid in pool
        if qid != last
    ]

    if not choices:
        choices = pool

    idx = random.choice(choices)

    context.user_data["last_qid"] = idx
    context.user_data["current_qid"] = idx

    item = cleaned_item(QUESTIONS[idx])

    options = item["options"][:4]

    keyboard = [
        [
            InlineKeyboardButton(
                f"{chr(65 + j)}. {option}",
                callback_data=f"ans:{idx}:{j}",
            )
        ]
        for j, option in enumerate(options)
    ]

    header = (
        f"📚 {item['course']}\n"
        f"📖 {item['module']}\n"
    )

    if item["test"]:
        header += f"📝 {item['test']}\n"

    await context.bot.send_message(
        chat_id,
        f"{header}\n"
        f"🧠 {item['q']}",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =========================================================
# JAWABAN
# =========================================================

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    # Wajib dijawab agar tombol Telegram tidak terus berputar.
    await query.answer()

    try:
        _, idx, chosen = query.data.split(":")
        idx = int(idx)
        chosen = int(chosen)

        item = cleaned_item(QUESTIONS[idx])

        # Jika soal rusak/tidak memiliki pilihan yang sesuai,
        # jangan biarkan bot crash.
        if chosen >= len(item["options"]):
            await query.message.reply_text(
                "⚠️ Soal ini memiliki format pilihan yang tidak lengkap."
            )
            return

        correct = chosen == item["answer"]

        record_answer(
            query.from_user.id,
            idx,
            correct,
        )

        result = "✅ BENAR!" if correct else "❌ BELUM TEPAT"

        explanation = item["explain"]

        # Pembahasan lama hanya berupa kalimat generik.
        # Tetap tampilkan, tetapi tidak mengarang pembahasan baru.
        if not explanation:
            explanation = "Pembahasan belum tersedia pada bank soal."

        key = item["key"]
        if not key:
            key = "Kunci ingatan belum tersedia pada bank soal."

        await query.edit_message_text(
            f"{result}\n\n"
            f"Jawaban benar:\n"
            f"{chr(65 + item['answer'])}. "
            f"{item['options'][item['answer']]}\n\n"
            f"💡 PEMBAHASAN\n"
            f"{explanation}\n\n"
            f"🔑 KUNCI INGATAN\n"
            f"{key}\n\n"
            f"📌 SUMBER\n"
            f"{item['course']} — "
            f"{item['module']} — "
            f"{item['test']}"
        )

        score, answered, wrong = stats(
            query.from_user.id
        )

        await context.bot.send_message(
            query.message.chat_id,
            (
                f"📊 Skor sementara: "
                f"{score}/{answered}\n"
                f"❌ Perlu diulang: {wrong}"
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "➡️ Soal berikutnya",
                            callback_data="next",
                        )
                    ]
                ]
            ),
        )

    except Exception as exc:
        # Supaya satu soal rusak tidak mematikan seluruh bot.
        print("ERROR ANSWER:", repr(exc))

        try:
            await query.message.reply_text(
                "⚠️ Terjadi kesalahan pada soal ini. "
                "Bot tetap berjalan. Silakan tekan /kuis untuk melanjutkan."
            )
        except Exception:
            pass


# =========================================================
# SOAL BERIKUTNYA
# =========================================================

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if context.user_data.get("mode") == "wrong":
        uid = query.from_user.id

        con = sqlite3.connect(DB)
        rows = con.execute(
            """
            SELECT question_id
            FROM wrong
            WHERE user_id=?
            """,
            (uid,),
        ).fetchall()
        con.close()

        pool = [row[0] for row in rows]

        if not pool:
            await query.message.reply_text(
                "🎉 Semua soal yang sebelumnya salah sudah benar!"
            )
            return

    else:
        pool = context.user_data.get("pool")

    await send_question(
        query.message.chat_id,
        context,
        query.from_user.id,
        pool,
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(update, context):
    print("BOT ERROR:", repr(context.error))


# =========================================================
# MAIN
# =========================================================

def main():
    token = os.environ.get("BOT_TOKEN")

    if not token:
        raise RuntimeError(
            "BOT_TOKEN belum diatur di Environment Variables FadeHost."
        )

    init_db()

    app = (
        Application
        .builder()
        .token(token)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("kuis", kuis)
    )

    app.add_handler(
        CommandHandler("skor", skor)
    )

    app.add_handler(
        CommandHandler("salah", salah)
    )

    app.add_handler(
        CallbackQueryHandler(
            choose_course,
            pattern=r"^course:",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            choose_module,
            pattern=r"^module:",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            back_courses,
            pattern=r"^back:courses$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            answer,
            pattern=r"^ans:\d+:\d+$",
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            next_question,
            pattern=r"^next$",
        )
    )

    app.add_error_handler(error_handler)

    print("🤖 Belajar Hukum Bot sedang berjalan...")

    app.run_polling()


if __name__ == "__main__":
    main()
