import json
import os

MEMORY_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "memory.json"
)


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except:
        return {}


def save_memory(memory):
    os.makedirs(
        os.path.dirname(MEMORY_FILE),
        exist_ok=True
    )

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