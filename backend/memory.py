import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
MEMORY_FILE = os.path.join(DATA_DIR, "memory.json")


def load_memory():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(MEMORY_FILE):
        return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {}


def save_memory(memory):
    os.makedirs(DATA_DIR, exist_ok=True)

    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            memory,
            file,
            ensure_ascii=False,
            indent=4
        )


def update_memory(key, value):
    memory = load_memory()

    value = str(value).strip()

    if not value:
        return

    memory[key] = value
    save_memory(memory)