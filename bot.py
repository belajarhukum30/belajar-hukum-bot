import os, json, sqlite3, random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

DB = "quiz.db"
with open("questions.json", "r", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

COURSES = sorted({q["course"] for q in QUESTIONS})

def init_db():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, score INTEGER DEFAULT 0, answered INTEGER DEFAULT 0)")
    con.execute("CREATE TABLE IF NOT EXISTS wrong (user_id INTEGER, question_id INTEGER, times_wrong INTEGER DEFAULT 1, PRIMARY KEY(user_id, question_id))")
    con.commit(); con.close()

def save_user(u):
    con=sqlite3.connect(DB)
    con.execute("INSERT OR IGNORE INTO users(user_id,name) VALUES(?,?)", (u.id,u.full_name))
    con.execute("UPDATE users SET name=? WHERE user_id=?", (u.full_name,u.id))
    con.commit(); con.close()

def record_answer(uid,qid,correct):
    con=sqlite3.connect(DB)
    con.execute("UPDATE users SET answered=answered+1, score=score+? WHERE user_id=?",(1 if correct else 0,uid))
    if correct:
        con.execute("DELETE FROM wrong WHERE user_id=? AND question_id=?",(uid,qid))
    else:
        con.execute("INSERT INTO wrong(user_id,question_id,times_wrong) VALUES(?,?,1) ON CONFLICT(user_id,question_id) DO UPDATE SET times_wrong=times_wrong+1",(uid,qid))
    con.commit(); con.close()

def stats(uid):
    con=sqlite3.connect(DB)
    row=con.execute("SELECT score,answered FROM users WHERE user_id=?",(uid,)).fetchone() or (0,0)
    wrong=con.execute("SELECT COUNT(*) FROM wrong WHERE user_id=?",(uid,)).fetchone()[0]
    con.close(); return row[0],row[1],wrong

def course_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(c, callback_data=f"course:{i}")] for i,c in enumerate(COURSES)])

def module_keyboard(course):
    mods=sorted({q["module"] for q in QUESTIONS if q["course"]==course}, key=lambda x:int(x.split()[-1]) if x.split()[-1].isdigit() else 999)
    rows=[[InlineKeyboardButton("📚 Semua modul", callback_data=f"module:{course}:all")]]
    rows += [[InlineKeyboardButton(m, callback_data=f"module:{course}:{m}")] for m in mods]
    rows += [[InlineKeyboardButton("⬅️ Mata kuliah", callback_data="back:courses")]]
    return InlineKeyboardMarkup(rows)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text(
        "📚 BELAJAR HUKUM — KUIS\n\n"
        "Sekarang tersedia bank soal dari 7 mata kuliah.\n"
        "Pilih mata kuliah, pilih modul, lalu jawab soal satu per satu.\n\n"
        "/kuis — mulai\n/skor — skor dan jumlah soal salah\n/salah — ulangi soal yang pernah salah"
    )
    await update.message.reply_text("Pilih mata kuliah:", reply_markup=course_keyboard())

async def kuis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    await update.message.reply_text("Pilih mata kuliah:", reply_markup=course_keyboard())

async def skor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user); s,a,w=stats(update.effective_user.id)
    pct=(s/a*100) if a else 0
    await update.message.reply_text(f"📊 Skor: {s}/{a} ({pct:.0f}%)\n❌ Soal yang masih perlu diulang: {w}")

async def salah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user)
    uid=update.effective_user.id
    con=sqlite3.connect(DB); rows=con.execute("SELECT question_id FROM wrong WHERE user_id=?",(uid,)).fetchall(); con.close()
    if not rows:
        await update.message.reply_text("🎉 Belum ada soal yang perlu diulang."); return
    context.user_data["mode"]="wrong"
    await send_question(update.effective_chat.id, context, uid, [r[0] for r in rows])

async def choose_course(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    i=int(q.data.split(":")[1]); course=COURSES[i]
    context.user_data["course"]=course
    await q.edit_message_text(f"📖 {course}\n\nPilih modul:", reply_markup=module_keyboard(course))

async def choose_module(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    _,course,module=q.data.split(":",2)
    context.user_data["course"]=course; context.user_data["module"]=module; context.user_data["mode"]="normal"
    ids=[i for i,x in enumerate(QUESTIONS) if x["course"]==course and (module=="all" or x["module"]==module)]
    if not ids:
        await q.edit_message_text("Belum ada soal pada pilihan ini."); return
    context.user_data["pool"]=ids
    await send_question(q.message.chat_id, context, q.from_user.id, ids)

async def back_courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); await q.edit_message_text("Pilih mata kuliah:", reply_markup=course_keyboard())

async def send_question(chat_id, context, uid, pool=None):
    if pool is None: pool=context.user_data.get("pool")
    if not pool:
        await context.bot.send_message(chat_id,"Belum ada bank soal untuk pilihan ini."); return
    # Avoid immediate repeats when possible.
    last=context.user_data.get("last_qid")
    choices=[i for i in pool if i!=last] or pool
    idx=random.choice(choices); context.user_data["last_qid"]=idx
    item=QUESTIONS[idx]
    context.user_data["current_qid"]=idx
    kb=[[InlineKeyboardButton(f"{chr(65+j)}. {opt}", callback_data=f"ans:{idx}:{j}")] for j,opt in enumerate(item["options"])]
    await context.bot.send_message(chat_id, f"🧠 {item['course']} • {item['module']}\n{item['test']}\n\n{item['q']}", reply_markup=InlineKeyboardMarkup(kb))

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    _,idx,chosen=q.data.split(":"); idx=int(idx); chosen=int(chosen)
    item=QUESTIONS[idx]; correct=chosen==item["answer"]
    record_answer(q.from_user.id,idx,correct)
    result="✅ BENAR" if correct else "❌ BELUM TEPAT"
    await q.edit_message_text(
        f"{result}\n\n"
        f"Jawaban benar: {chr(65+item['answer'])}. {item['options'][item['answer']]}\n\n"
        f"💡 Pembahasan:\n{item['explain']}\n\n"
        f"🔑 {item['key']}\n\n"
        f"📌 Sumber: {item['course']} — {item['module']} — {item['test']}"
    )
    s,a,w=stats(q.from_user.id)
    await context.bot.send_message(q.message.chat_id, f"📊 Skor sementara: {s}/{a}\n❌ Perlu diulang: {w}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Soal berikutnya", callback_data="next")]]))

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if context.user_data.get("mode")=="wrong":
        uid=q.from_user.id
        con=sqlite3.connect(DB); rows=con.execute("SELECT question_id FROM wrong WHERE user_id=?",(uid,)).fetchall(); con.close()
        pool=[r[0] for r in rows]
        if not pool:
            await q.message.reply_text("🎉 Semua soal yang sebelumnya salah sudah benar!"); return
    else:
        pool=context.user_data.get("pool")
    await send_question(q.message.chat_id, context, q.from_user.id, pool)

def main():
    token=os.environ.get("BOT_TOKEN")
    if not token: raise RuntimeError("BOT_TOKEN belum diatur")
    init_db()
    app=Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler("kuis",kuis)); app.add_handler(CommandHandler("skor",skor)); app.add_handler(CommandHandler("salah",salah))
    app.add_handler(CallbackQueryHandler(choose_course,pattern=r"^course:"))
    app.add_handler(CallbackQueryHandler(choose_module,pattern=r"^module:"))
    app.add_handler(CallbackQueryHandler(back_courses,pattern=r"^back:courses$"))
    app.add_handler(CallbackQueryHandler(answer,pattern=r"^ans:")); app.add_handler(CallbackQueryHandler(next_question,pattern=r"^next$"))
    app.run_polling()
if __name__=="__main__": main()
