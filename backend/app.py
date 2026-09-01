

from pyexpat.errors import messages

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from google import genai
import re

from chat_history import add_chat, load_history, delete_chat, rename_chat
from memory import load_memory, update_memory


app = Flask(__name__)
CORS(app)

MODEL = "gemini-3.6-flash"

client = genai.Client()

conversation_history = []
memory = load_memory()


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


def save_memory(key, value):
    value = clean_value(value)

    if not value:
        return

    update_memory(key, value)
    memory[key] = value

    print(f"Memory saved: {key} = {value}")


# ==========================================
# AUTOMATIC MEMORY DETECTION
# ==========================================

def detect_memory(message):

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
            r"^mera favorite game\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite game"
        ),

        (
            r"^my favorite game is\s+(.+?)[.!?]?$",
            "favorite game"
        ),

        (
            r"^mujhe\s+(.+?)\s+pasand\s+hai[.!?]?$",
            "preference"
        ),

        (
            r"^mera favorite color\s+(.+?)(?:\s+hai)?[.!?]?$",
            "favorite color"
        ),

        (
            r"^my favorite color is\s+(.+?)[.!?]?$",
            "favorite color"
        ),

        (
            r"^mera favorite programming language\s+(.+?)(?:\s+hai)?[.!?]?$",
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

            value_lower = value.lower()

            if value_lower in [
                "cricket",
                "football",
                "gaming",
                "coding",
                "programming",
                "python",
                "java",
                "javascript"
            ]:

                save_memory("favorite", value)

            return

        save_memory(key, value)
        return


# ==========================================
# PERSONAL QUESTIONS
# ==========================================

def personal_answer(message):

    text = message.lower().strip()
    text = re.sub(r"[?.!]", "", text)

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
        if "name" in memory:
            return f"Tumhara naam {memory['name']} hai."

        return "Mujhe abhi tumhara naam nahi pata."

    # FAVORITE GAME
    if "mera favorite game kya hai" in text:
        if "favorite game" in memory:
            return f"Tumhara favorite game {memory['favorite game']} hai."

        return "Mujhe abhi tumhara favorite game nahi pata."

    # FAVORITE COLOR
    if "mera favorite color kya hai" in text:
        if "favorite color" in memory:
            return f"Tumhara favorite color {memory['favorite color']} hai."

        return "Mujhe abhi tumhara favorite color nahi pata."

    # FAVORITE
    if "mera favorite kya hai" in text:
        if "favorite" in memory:
            return f"Tumhe {memory['favorite']} pasand hai."

        return "Mujhe abhi tumhara favorite nahi pata."

    # COLLEGE
    if any(x in text for x in [
        "mera college kya hai",
        "mera college ka kya naam hai",
        "mere college ka kya naam hai",
        "what is my college"
    ]):
        if "college" in memory:
            return f"Tumhara college {memory['college']} hai."

        return "Mujhe abhi tumhara college nahi pata."

    # GOAL
    if "mera goal kya hai" in text:
        if "goal" in memory:
            return f"Tumhara goal {memory['goal']} hai."

        return "Mujhe abhi tumhara goal nahi pata."

    # CITY
    if "meri city kya hai" in text:
        if "city" in memory:
            return f"Tumhari city {memory['city']} hai."

        return "Mujhe abhi tumhari city nahi pata."

    return None


# ==========================================
# HOME
# ==========================================

@app.route("/")
def home():

    return jsonify({
        "app": "Normal Chat",
        "status": "Backend is running"
    })


# ==========================================
# CHAT
# ==========================================

@app.route("/chat", methods=["POST"])
def chat():

    global conversation_history

    try:

        data = request.get_json()

        if not data or "message" not in data:
            return jsonify({
                "error": "Message is missing"
            }), 400

        message = str(data["message"]).strip()

        if not message:
            return jsonify({
                "error": "Message is empty"
            }), 400

        history_from_frontend = data.get(
            "history",
            []
        )

        # PERSONAL QUESTION
        direct_reply = personal_answer(message)

        if direct_reply:

            conversation_history.append({
                "role": "user",
                "content": message
            })

            conversation_history.append({
                "role": "assistant",
                "content": direct_reply
            })

            return jsonify({
                "reply": direct_reply
            })

        # MEMORY
        detect_memory(message)

        # ======================================
        # MEMORY TEXT
        # ======================================

        memory_text = ""

        for key, value in memory.items():
            memory_text += f"{key}: {value}\n"

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
        # OLLAMA MESSAGES
        # ======================================

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        if history_from_frontend:

    # Frontend history me current user message already hai,
    # isliye last message ko dobara add nahi karna.
          messages.extend(
        history_from_frontend[-11:-1]
      )

        else:

          messages.extend(
        conversation_history[-10:]
    )
        messages.append({
            "role": "user",
            "content": message
        })
 
                # ======================================
        # GEMINI
        # ======================================

        prompt = system_prompt + "\n\nConversation:\n"

        for msg in messages[1:]:
            role = msg["role"]
            content = msg["content"]

            prompt += f"{role}: {content}\n"

        max_retries = 3
        reply = None

        for attempt in range(max_retries):

            try:

                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt
                )

                reply = response.text.strip()

                if reply:
                    break

            except Exception as gemini_error:

                error_text = str(gemini_error)

                print(
                    f"Gemini attempt {attempt + 1} failed:",
                    error_text
                )

                if "503" in error_text:

                    import time

                    time.sleep(2 ** attempt)

                else:

                    raise

        if not reply:

            raise Exception(
                "Gemini abhi available nahi hai. Thodi der baad try karo."
            )
        # ======================================
        # SAVE CONVERSATION
        # ======================================

        conversation_history.append({
            "role": "user",
            "content": message
        })

        conversation_history.append({
            "role": "assistant",
            "content": reply
        })

        return jsonify({
            "reply": reply
        })

    except Exception as error:

        print("Backend error:", error)

        return jsonify({
            "error": str(error)
        }), 500


# ==========================================
# HISTORY
# ==========================================

@app.route("/history", methods=["GET"])
def history():

    try:

        return jsonify({
            "history": load_history()
        })

    except Exception as error:

        return jsonify({
            "error": str(error)
        }), 500


# ==========================================
# NEW CHAT
# ==========================================

@app.route("/new-chat", methods=["POST"])
def new_chat():

    global conversation_history

    # Purani conversation ko history me save karo
    if conversation_history:

        add_chat(conversation_history)

    conversation_history = []

    return jsonify({
        "message": "New chat started"
    })


# ==========================================
# DELETE HISTORY
# ==========================================

@app.route("/history/<int:index>", methods=["DELETE"])
def delete_history(index):

    try:

        success = delete_chat(index)

        if not success:

            return jsonify({
                "error": "Chat not found"
            }), 404

        return jsonify({
            "message": "Chat deleted"
        })

    except Exception as error:

        return jsonify({
            "error": str(error)
        }), 500


# ==========================================
# RENAME HISTORY
# ==========================================

@app.route(
    "/history/<int:index>/rename",
    methods=["POST", "PUT"]
)
def rename_history(index):

    try:

        data = request.get_json()

        if not data:

            return jsonify({
                "error": "Request data missing"
            }), 400

        # Frontend "name" bhej raha hai
        # Backend "title" bhi accept karega

        title = data.get("name")

        if title is None:
            title = data.get("title")

        if title is None:

            return jsonify({
                "error": "Name is missing"
            }), 400

        title = str(title).strip()

        if not title:

            return jsonify({
                "error": "Name cannot be empty"
            }), 400

        title = title[:40]

        success = rename_chat(
            index,
            title
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

        print("Rename error:", error)

        return jsonify({
            "error": str(error)
        }), 500


# ==========================================
# START
# ==========================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )