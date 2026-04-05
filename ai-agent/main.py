from fastapi import FastAPI
from fastapi.responses import RedirectResponse
import sqlite3
import os
import google.generativeai as genai

app = FastAPI()

# ---------------- GEMINI SETUP ---------------- #

API_KEY = os.getenv("GEMINI API KEY")

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("gemini-pro")
else:
    model = None

# ---------------- DATABASE ---------------- #

conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, task TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, event TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, note TEXT)")
conn.commit()

# ---------------- TOOLS (SUB-AGENTS) ---------------- #

def task_tool(text):
    cursor.execute("INSERT INTO tasks (task) VALUES (?)", (text,))
    conn.commit()
    return f"Task created: {text}"

def calendar_tool(text):
    cursor.execute("INSERT INTO events (event) VALUES (?)", (text,))
    conn.commit()
    return f"Event scheduled: {text}"

def notes_tool(text):
    cursor.execute("INSERT INTO notes (note) VALUES (?)", (text,))
    conn.commit()
    return f"Note saved: {text}"

# ---------------- DELETE OPERATIONS ---------------- #

def delete_tasks():
    cursor.execute("DELETE FROM tasks")
    conn.commit()
    return "All tasks deleted"

def delete_events():
    cursor.execute("DELETE FROM events")
    conn.commit()
    return "All events deleted"

def delete_notes():
    cursor.execute("DELETE FROM notes")
    conn.commit()
    return "All notes deleted"

# ---------------- RETRIEVAL ---------------- #

def get_tasks():
    cursor.execute("SELECT task FROM tasks")
    return [row[0] for row in cursor.fetchall()]

def get_events():
    cursor.execute("SELECT event FROM events")
    return [row[0] for row in cursor.fetchall()]

def get_notes():
    cursor.execute("SELECT note FROM notes")
    return [row[0] for row in cursor.fetchall()]

# ---------------- GEMINI ROUTING ---------------- #

def decide_with_gemini(user_input):
    if not model:
        return None

    try:
        prompt = f"""
        Classify the user input into one of the following:
        task, calendar, notes, delete, retrieve, workflow

        Input: {user_input}
        Output ONLY one word.
        """

        response = model.generate_content(prompt)

        if response.text:
            return response.text.strip().lower()

    except Exception as e:
        print("Gemini error:", e)

    return None

# ---------------- PRIMARY AGENT ---------------- #

def primary_agent(user_input: str):
    text = user_input.lower()

    # -------- GEMINI INTENT -------- #
    intent = decide_with_gemini(user_input)

    # -------- MULTI-STEP WORKFLOW -------- #
    if "meeting" in text and "prepare" in text:
        task_tool("Prepare for meeting")
        calendar_tool("Meeting scheduled")
        return {
            "workflow": "multi-step",
            "actions": ["task created", "meeting scheduled"]
        }

    # -------- DELETE (IMPORTANT: FIRST) -------- #
    if "delete" in text:
        if "task" in text:
            return {"action": "delete", "result": delete_tasks()}
        elif "event" in text or "meeting" in text:
            return {"action": "delete", "result": delete_events()}
        elif "note" in text:
            return {"action": "delete", "result": delete_notes()}

    # -------- RETRIEVE -------- #
    if "show tasks" in text:
        return {"tasks": get_tasks()}

    if "show events" in text:
        return {"events": get_events()}

    if "show notes" in text:
        return {"notes": get_notes()}

    # -------- GEMINI ROUTING -------- #
    if intent:
        if "task" in intent:
            return {"agent": "task_agent", "result": task_tool(user_input)}

        elif "calendar" in intent:
            return {"agent": "calendar_agent", "result": calendar_tool(user_input)}

        elif "notes" in intent:
            return {"agent": "notes_agent", "result": notes_tool(user_input)}

    # -------- FALLBACK LOGIC -------- #
    if "task" in text or "todo" in text:
        return {"agent": "task_agent", "result": task_tool(user_input)}

    elif "schedule" in text or "meeting" in text:
        return {"agent": "calendar_agent", "result": calendar_tool(user_input)}

    elif "note" in text:
        return {"agent": "notes_agent", "result": notes_tool(user_input)}

    return {"message": "Could not understand request"}

# ---------------- API ---------------- #

@app.get("/")
def home():
    return RedirectResponse(url="/docs")

@app.post("/agent")
def run_agent(input: str):
    return primary_agent(input)