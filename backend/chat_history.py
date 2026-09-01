import json
import os


HISTORY_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "chat_history.json"
)


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except Exception:
        return []


def save_history(history):

    os.makedirs(
        os.path.dirname(HISTORY_FILE),
        exist_ok=True
    )

    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            history,
            file,
            indent=4,
            ensure_ascii=False
        )


def add_chat(messages, title=None):

    if not messages:
        return

    history = load_history()

    if title is None:

        title = "New Chat"

        for message in messages:

            if message.get("role") == "user":

                title = message.get(
                    "content",
                    "New Chat"
                )

                break

        title = str(title)[:40]

    history.append({
        "title": title,
        "messages": messages
    })

    save_history(history)


def delete_chat(index):

    history = load_history()

    if index < 0 or index >= len(history):
        return False

    history.pop(index)

    save_history(history)

    return True


def rename_chat(index, title):

    history = load_history()

    if index < 0 or index >= len(history):
        return False

    title = str(title).strip()

    if not title:
        return False

    history[index]["title"] = title[:40]

    save_history(history)

    return True