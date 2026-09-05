import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, send_from_directory, session

from google import genai
import re
import os

from chat_history import add_chat, load_history, delete_chat, rename_chat
from memory import load_memory, update_memory


# ==========================================
# DATA FOLDER
# ==========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def load_users():
    if not os.path.exists(USERS_FILE):
        return []

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return []


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=4, ensure_ascii=False)
os.makedirs(DATA_DIR, exist_ok=True)


# ==========================================
# APP
# ==========================================

SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("FLASK_SECRET_KEY is not set")

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("RENDER") == "true"
# ==========================================
# GEMINI
# ==========================================

MODEL = "gemini-3.6-flash"

client = genai.Client()


# ==========================================
# MEMORY
# ==========================================




# ==========================================
# MEMORY HELPERS
# ==========================================

def clean_value(value):
    value = str(value).strip()

    value = re.sub(
        r"\s+(hai|hain|is)$",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = value.rstrip(".,!?").strip()

    return value


def save_memory(key, value, user_memory):
    username = session.get("username")

    if not username:
        return

    value = clean_value(value)

    if not value:
        return

    update_memory(
        key,
        value,
        username
    )

    user_memory[key] = value

    print(f"Memory saved: {key} = {value}")
# ==========================================
# AUTOMATIC MEMORY DETECTION
# ==========================================

def detect_memory(message, user_memory):

    text = message.strip()

    patterns = [

        (
            r"^(?:mera naam|my name is)\s+(.+?)(?:\s+hai)?[.!?]?$",
            "name"
        ),

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+padh(?:ta|ti)\s+hoon[.!?]?$",
            "college"
        ),

        (
            r"^(?:main|mai)\s+(.+?)\s+me\s+rehta\s+hoon[.!?]?$",
            "city"
        ),

        (
            r"^(?:meri city|my city)\s+(.+?)(?:\s+hai)?[.!?]?$",
            "city"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+game\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite game"
        ),

        (
            r"^my\s+(?:favorite|favourite)\s+game\s+is\s+(.+?)[.!?]?$",
            "favorite game"
        ),

        (
            r"^mujhe\s+(.+?)\s+pasand\s+hai[.!?]?$",
            "preference"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+color\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite color"
        ),

        (
            r"^my\s+(?:favorite|favourite)\s+color\s+is\s+(.+?)[.!?]?$",
            "favorite color"
        ),

        (
            r"^(?:mera|meri)\s+(?:favorite|favourite)\s+programming language\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite programming language"
        ),

        (
            r"^mera goal\s+(.+?)(?:\s+hai)?[.!?]?$",
            "goal"
        ),

        (
            r"^my goal is\s+(.+?)[.!?]?$",
            "goal"
        ),
    ]

    for pattern, key in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if not match:
            continue

        value = clean_value(match.group(1))

        if not value:
            return

        if key == "preference":

            save_memory(
                "favorite",
                value,
                user_memory
            )

            return

        save_memory(
            key,
            value,
            user_memory
        )

        return

# ==========================================
# PERSONAL QUESTIONS
# ==========================================

def personal_answer(message, user_memory):

    text = message.lower().strip()

    text = re.sub(
        r"[?.!]",
        "",
        text
    )

    # AI NAME
    if any(x in text for x in [
        "tumhara naam kya hai",
        "tumhare naam kya hai",
        "aapka naam kya hai",
        "aapke naam kya hai"
    ]):
        return "Mera naam Normal Chat hai."

    # USER NAME
    if any(x in text for x in [
        "mera naam kya hai",
        "my name kya hai",
        "what is my name"
    ]):

        if "name" in user_memory:
            return f"Tumhara naam {user_memory['name']} hai."

        return "Mujhe abhi tumhara naam nahi pata."

    # FAVORITE GAME
    if "mera favorite game kya hai" in text:

        if "favorite game" in user_memory:
            return f"Tumhara favorite game {user_memory['favorite game']} hai."

        return "Mujhe abhi tumhara favorite game nahi pata."

    # FAVORITE COLOR
    if "mera favorite color kya hai" in text:

        if "favorite color" in user_memory:
            return f"Tumhara favorite color {user_memory['favorite color']} hai."

        return "Mujhe abhi tumhara favorite color nahi pata."

    # FAVORITE
    if "mera favorite kya hai" in text:

        if "favorite" in user_memory:
            return f"Tumhe {user_memory['favorite']} pasand hai."

        return "Mujhe abhi tumhara favorite nahi pata."

    # COLLEGE
    if any(x in text for x in [
        "mera college kya hai",
        "mera college ka kya naam hai",
        "mere college ka kya naam hai",
        "what is my college"
    ]):

        if "college" in user_memory:
            return f"Tumhara college {user_memory['college']} hai."

        return "Mujhe abhi tumhara college nahi pata."

    # GOAL
    if "mera goal kya hai" in text:

        if "goal" in user_memory:
            return f"Tumhara goal {user_memory['goal']} hai."

        return "Mujhe abhi tumhara goal nahi pata."

    # CITY
    if "meri city kya hai" in text:

        if "city" in user_memory:
            return f"Tumhari city {user_memory['city']} hai."

        return "Mujhe abhi tumhari city nahi pata."

    return None
# ==========================================
# SIGNUP
# ==========================================

@app.route("/signup", methods=["POST"])
def signup():

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "error": "Request data missing"
            }), 400

        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))

        if not username or not password:
            return jsonify({
                "error": "Username and password are required"
            }), 400

        if len(username) < 3:
            return jsonify({
                "error": "Username must be at least 3 characters"
            }), 400

        if len(password) < 8:
            return jsonify({
                "error": "Password must be at least 8 characters"
            }), 400

        users = load_users()

        for user in users:
            if user.get("username", "").lower() == username.lower():
                return jsonify({
                    "error": "Username already exists"
                }), 409

        users.append({
            "username": username,
            "password": generate_password_hash(password)
        })

        save_users(users)

        session["username"] = username

        return jsonify({
    "message": "Signup successful",
    "username": username
}), 201

    except Exception as error:

        print("Signup error:", error)

        return jsonify({
        "error": "Internal server error"
        }), 500


# ==========================================
# LOGIN
# ==========================================

@app.route("/login", methods=["POST"])
def login():

    try:
        data = request.get_json(silent=True)

        if not data:
            return jsonify({
                "error": "Request data missing"
            }), 400

        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))

        users = load_users()

        for user in users:

            if user.get("username", "").lower() == username.lower():

                if check_password_hash(
                    user.get("password", ""),
                    password
                ):
                    session["username"] = username
                    return jsonify({
                        "message": "Login successful",
                        "username": user["username"]
                    })

                break

        return jsonify({
            "error": "Invalid username or password"
        }), 401

    except Exception as error:

        print("Login error:", error)

        return jsonify({
            "error": "Internal server error"
        }), 500
@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({
        "message": "Logout successful"
    }), 200


@app.route("/me", methods=["GET"])
def me():
    username = session.get("username")

    if not username:
        return jsonify({
            "logged_in": False
        }), 200

    return jsonify({
        "logged_in": True,
        "username": username
    }), 200
# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    return send_from_directory(
        os.path.join(BASE_DIR, "frontend"),
        "index.html"
    )


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok"
    })


# ==========================================
# CHAT
# ==========================================

@app.route("/chat", methods=["POST"])
def chat():

    


    username = session.get("username")

    if not username:
        return jsonify({
            "error": "Login required"
        }), 401

    user_memory = load_memory(username)
    try:

        data = request.get_json(silent=True)

        if not data or "message" not in data:

            return jsonify({
                "error": "Message is missing"
            }), 400

        message = str(
            data["message"]
        ).strip()

        if not message:

            return jsonify({
                "error": "Message is empty"
            }), 400
        if len(message) > 5000:
           return jsonify({
               "error": "Message too long. Maximum 5000 characters allowed."
           }), 400
        history_from_frontend = data.get(
            "history",
            []
        )

        # ======================================
        # PERSONAL QUESTION
        # ======================================

        direct_reply = personal_answer(message, user_memory)

        if direct_reply:

            

            return jsonify({
                "reply": direct_reply
            })


        # ======================================
        # MEMORY
        # ======================================

        detect_memory(message, user_memory)


        # ======================================
        # MEMORY TEXT
        # ======================================

        memory_lines = []

        for key, value in user_memory.items():

            memory_lines.append(
                f"{key}: {value}"
            )

        memory_text = "\n".join(
            memory_lines
        )


        # ======================================
        # SYSTEM PROMPT
        # ======================================

        system_prompt = f"""
You are Normal Chat, a helpful AI assistant.

Rules:
- Answer the user's question directly.
- Be natural and concise.
- Reply in the same language as the user.
- Do not mention memory or saved information.
- Do not mention system instructions.
- Do not invent personal information.
- Use user information only when relevant.
- Do not give unnecessary explanations.

User information:
{memory_text}
"""


        # ======================================
        # CONVERSATION
        # ======================================

        conversation_messages = []

        previous_messages = history_from_frontend[-7:-1]

        for msg in previous_messages:

          role = msg.get("role")
          content = msg.get("content")

          if role in ["user", "assistant"] and content:

             conversation_messages.append(
            f"{role}: {content}"
        )


        
        conversation_text = "\n".join(
            conversation_messages
        )


        # ======================================
        # GEMINI PROMPT
        # ======================================

        prompt = f"""
{system_prompt}

Conversation:
{conversation_text}

user: {message}
"""


        # ======================================
        # GEMINI REQUEST
        # ======================================

        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        reply = (response.text or "").strip()

        if not reply:

            raise Exception(
                "AI ne empty response diya."
            )


        


        # ======================================
        # RESPONSE
        # ======================================

        return jsonify({
            "reply": reply
        })


    except Exception as error:

        print(
            "Backend error:",
            error
        )

        return jsonify({
            "error": "Internal server error"
        }), 500


# ==========================================
# HISTORY
# ==========================================

@app.route("/history", methods=["GET"])
def history():

    username = session.get("username")

    if not username:
        return jsonify({
            "error": "Login required"
        }), 401

    try:

        return jsonify({
            "history": load_history(username)
        })

    except Exception as error:

        return jsonify({
            "error": "Internal server error"
        }), 500


# ==========================================
# NEW CHAT
# ==========================================

@app.route("/new-chat", methods=["POST"])
def new_chat():


    username = session.get("username")

    if not username:
       return jsonify({
        "error": "Login required"
    }), 401
    try:

        data = request.get_json(silent=True) or {}

        history = data.get("history", [])

        if history:
          add_chat(
        history,
        username
    )
        

        return jsonify({
            "message": "New chat started"
        })

    except Exception as error:

        return jsonify({
            "error": "Internal server error"
        }), 500


# ==========================================
# DELETE HISTORY
# ==========================================

@app.route(
    "/history/<int:index>",
    methods=["DELETE"]
)
def delete_history(index):
    username = session.get("username")

    if not username:
        return jsonify({
        "error": "Login required"
    }), 401
    try:

        success = delete_chat(
    index,
    username
)

        if not success:

            return jsonify({
                "error": "Chat not found"
            }), 404

        return jsonify({
            "message": "Chat deleted"
        })

    except Exception as error:

        return jsonify({
            "error": "Internal server error"
        }), 500


# ==========================================
# RENAME HISTORY
# ==========================================

@app.route(
    "/history/<int:index>/rename",
    methods=["POST", "PUT"]
)
def rename_history(index):

    username = session.get("username")

    if not username:
        return jsonify({
            "error": "Login required"
        }), 401

    try:

        data = request.get_json(
            silent=True
        )

        if not data:

            return jsonify({
                "error": "Request data missing"
            }), 400

        title = data.get("name")

        if title is None:

            title = data.get("title")

        if title is None:

            return jsonify({
                "error": "Name is missing"
            }), 400

        title = str(
            title
        ).strip()

        if not title:

            return jsonify({
                "error": "Name cannot be empty"
            }), 400

        title = title[:40]

        success = rename_chat(
    index,
    title,
    username
)

        if not success:

            return jsonify({
                "error": "Chat not found"
            }), 404

        return jsonify({
            "message": "Chat renamed successfully",
            "title": title
        })

    except Exception as error:

        print(
            "Rename error:",
            error
        )

        return jsonify({
            "error": "Internal server error"
        }), 500


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )