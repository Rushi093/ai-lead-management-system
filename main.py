from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime
import os
import json
import sqlite3


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env file.")

client = Groq(api_key=GROQ_API_KEY)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


DB_PATH = "leads.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS developers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        role TEXT,
        service_category TEXT,
        skills TEXT,
        available INTEGER,
        max_workload INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        email TEXT,
        source TEXT,
        message TEXT,
        interested_service TEXT,
        timestamp TEXT,
        lead_status TEXT,
        ai_summary TEXT,
        is_spam INTEGER,
        spam_reason TEXT,
        follow_up_priority TEXT,
        assigned_developer_id INTEGER
    )
    """)
    
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        lead_id INTEGER,
        role TEXT,
        message TEXT
    )
    """)
    
    
    cursor.execute("SELECT COUNT(*) FROM developers")
    if cursor.fetchone()[0] == 0:
        default_devs = [
            ("Rahul", "Web Developer", "Website Development", "HTML, CSS, JavaScript, React, FastAPI", 1, 3),
            ("Priya", "Application Developer", "Application Development", "Flutter, Android, Firebase, API Integration", 1, 3),
            ("Amit", "Backend Developer", "Backend Development", "Python, FastAPI, PostgreSQL, MySQL", 1, 3),
            ("Neha", "UI/UX Designer", "UI/UX Design", "Figma, Wireframe, Prototype, Web Design", 1, 3),
            ("Karan", "Digital Marketing Specialist", "Digital Marketing", "SEO, Google Ads, Social Media Marketing", 1, 3)
        ]
        cursor.executemany("""
        INSERT INTO developers (name, role, service_category, skills, available, max_workload)
        VALUES (?, ?, ?, ?, ?, ?)
        """, default_devs)
        
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


class LeadInput(BaseModel):
    name: str
    phone: str
    email: EmailStr
    source: str
    message: str
    interested_service: str

class ChatInput(BaseModel):
    lead_id: int
    message: str


def analyze_lead_with_ai(lead: LeadInput):
    """Ask AI to qualify and analyze a new lead."""
    prompt = f"""
    Analyze this lead and return a JSON object ONLY:
    Name: {lead.name}
    Message: {lead.message}
    Interested Service: {lead.interested_service}
    
    Return JSON in exactly this format:
    {{
      "lead_status": "Hot" or "Warm" or "Cold",
      "ai_summary": "one line summary of customer request",
      "is_spam": true or false,
      "spam_reason": "why spam or 'Not spam'",
      "follow_up_priority": "High" or "Medium" or "Low"
    }}
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a lead analyst. Return ONLY valid JSON. No markdown code blocks."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        return json.loads(response.choices[0].message.content.strip())
    except Exception:
        return {
            "lead_status": "Warm",
            "ai_summary": "Manual follow-up required",
            "is_spam": False,
            "spam_reason": "Not spam",
            "follow_up_priority": "Medium"
        }

def assign_developer_basic(service: str):
    """Simple developer matching based on service category."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM developers WHERE LOWER(service_category) = ?", (service.lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["id"], row["name"]
    return 1, "Rahul"


@app.get("/")
def home():
    return {"message": "Simple AI Lead System is active"}

@app.get("/developers")
def get_developers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM developers")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/leads")
def get_leads():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT l.*, d.name AS assigned_dev_name
    FROM leads l
    LEFT JOIN developers d ON l.assigned_developer_id = d.id
    ORDER BY l.id DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/capture-lead")
def capture_lead(lead: LeadInput):
    ai_result = analyze_lead_with_ai(lead)
    
    conn = get_db()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO leads (name, phone, email, source, message, interested_service, timestamp, lead_status, ai_summary, is_spam, spam_reason, follow_up_priority, assigned_developer_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
    """, (
        lead.name, lead.phone, lead.email, lead.source, lead.message, lead.interested_service,
        timestamp, ai_result["lead_status"], ai_result["ai_summary"],
        1 if ai_result["is_spam"] else 0, ai_result["spam_reason"], ai_result["follow_up_priority"]
    ))
    conn.commit()
    lead_id = cursor.lastrowid
    
    # Save message to conversation history
    cursor.execute("""
    INSERT INTO conversations (lead_id, role, message, timestamp)
    VALUES (?, 'user', ?, ?)
    """, (lead_id, lead.message, timestamp))
    conn.commit()
    conn.close()
    
    return {"lead_id": lead_id, "lead_status": ai_result["lead_status"]}

@app.post("/chat")
def chat_with_lead(chat: ChatInput):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM leads WHERE id = ?", (chat.lead_id,))
    lead = cursor.fetchone()
    if not lead:
        conn.close()
        raise HTTPException(status_code=404, detail="Lead not found")
    lead = dict(lead)
    
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO conversations (lead_id, role, message, timestamp)
    VALUES (?, 'user', ?, ?)
    """, (chat.lead_id, chat.message, timestamp))
    conn.commit()

    cursor.execute("SELECT * FROM conversations WHERE lead_id = ?", (chat.lead_id,))
    history = cursor.fetchall()
    history_list = [{"role": r["role"], "message": r["message"]} for r in history]
    
    prompt = f"""
    You are an AI sales assistant for an IT service company.
    Client name: {lead['name']}
    Service Category: {lead['interested_service']}
    
    History of conversation:
    {history_list}
    
    New user message:
    {chat.message}
    
    Reply in simple Hinglish. Ask one short follow-up question.
    Detect if they want to finalize or proceed (e.g. they say yes, confirm, proceed, start, banana start karo, etc.).
    
    Return JSON in exactly this format:
    {{
      "reply": "your assistant chat response here",
      "completed": true or false
    }}
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a friendly sales assistant. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        ai_res = json.loads(response.choices[0].message.content.strip())
        ai_reply = ai_res.get("reply", "Great!")
        completed = ai_res.get("completed", False)
    except Exception:
        ai_reply = "Hum details aage forward karein?"
        completed = False
        
    assigned_dev_name = None
    if completed:
        dev_id, assigned_dev_name = assign_developer_basic(lead["interested_service"])
        cursor.execute("UPDATE leads SET assigned_developer_id = ? WHERE id = ?", (dev_id, chat.lead_id))
        conn.commit()
        ai_reply = f"Great! Aapka requirement confirm ho karka developer '{assigned_dev_name}' ko assign ho gaya hai."

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
    INSERT INTO conversations (lead_id, role, message, timestamp)
    VALUES (?, 'assistant', ?, ?)
    """, (chat.lead_id, ai_reply, timestamp))
    conn.commit()
    conn.close()
    
    return {
        "lead_id": chat.lead_id,
        "ai_reply": ai_reply,
        "conversation_completed": completed,
        "assigned_developer": {"name": assigned_dev_name} if assigned_dev_name else None
    }

@app.get("/conversation/{lead_id}")
def get_conversation(lead_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM conversations WHERE lead_id = ?", (lead_id,))
    history = cursor.fetchall()
    
    cursor.execute("""
    SELECT d.name 
    FROM leads l
    LEFT JOIN developers d ON l.assigned_developer_id = d.id
    WHERE l.id = ?
    """, (lead_id,))
    lead = cursor.fetchone()
    conn.close()
    
    assigned_dev_name = lead[0] if lead and lead[0] else None
    
    return {
        "conversation": [{"role": r["role"], "message": r["message"]} for r in history],
        "assigned_dev": assigned_dev_name
    }