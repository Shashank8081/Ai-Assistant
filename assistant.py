import os
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
import webbrowser

# ---------------- Dependencies ----------------
try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    import pyttsx3
except Exception:
    pyttsx3 = None

try:
    import wikipedia
    from wikipedia.exceptions import DisambiguationError, PageError
except Exception:
    wikipedia = None

try:
    import openai
except Exception:
    openai = None

# ---------------- Data persistence ----------------
DATA_DIR = Path.home() / ".shree_voice"
DATA_DIR.mkdir(exist_ok=True)
TODO_FILE = DATA_DIR / "todo.json"

def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path, data):
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"Error saving {path}: {e}")

todo_list = load_json(TODO_FILE, [])

# ---------------- Speaker ----------------
class Speaker:
    def __init__(self):
        self.enabled = False
        if pyttsx3:
            try:
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", 175)  # more natural speed
                self.enabled = True
            except Exception:
                self.engine = None
        else:
            self.engine = None

    def say(self, text: str, wait=True):
        print("Shree:", text)
        if self.enabled and self.engine:
            try:
                self.engine.say(text)
                if wait:
                    self.engine.runAndWait()
                else:
                    threading.Thread(target=self.engine.runAndWait, daemon=True).start()
            except Exception as e:
                print("TTS error:", e)

# ---------------- Listener ----------------
class Listener:
    def __init__(self):
        if not sr:
            raise RuntimeError("SpeechRecognition not installed. Run: pip install SpeechRecognition pyaudio")
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    def listen(self, timeout=6, phrase_time_limit=10) -> Optional[str]:
        with self.microphone as source:
            print("(Listening...)")
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            except Exception:
                pass
            try:
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                return None
        try:
            text = self.recognizer.recognize_google(audio)
            print("User:", text)
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print("Speech API error:", e)
            return None

# ---------------- Assistant ----------------
class ShreeVoice:
    def __init__(self):
        self.speaker = Speaker()
        try:
            self.listener = Listener()
        except Exception as e:
            self.listener = None
            print("Listener unavailable:", e)

        self.openai_key = os.environ.get("OPENAI_API_KEY")
        if openai and self.openai_key:
            openai.api_key = self.openai_key

        self.running = True
        self.chat_history = []  # conversation context

    def handle_command(self, text: str) -> str:
        lower = text.lower().strip()

        # simple commands
        if lower in ("hi", "hello", "hey"):
            return "Hello! How are you today?"
        if lower.startswith("open "):
            return self._open_website(text[5:].strip())
        if lower.startswith("add todo "):
            return self._add_todo(text[9:].strip())
        if lower in ("list todo", "show todo", "todos"):
            return self._list_todo()

        # otherwise → AI response
        return self._answer_with_ai(text)

    def _open_website(self, target: str) -> str:
        shortcuts = {
            "youtube": "https://www.youtube.com",
            "google": "https://www.google.com",
            "github": "https://github.com"
        }
        url = shortcuts.get(target.lower(), f"https://www.google.com/search?q={target.replace(' ', '+')}")
        webbrowser.open(url)
        return f"Opening {target}"

    def _add_todo(self, item: str) -> str:
        todo_list.append({"item": item, "added_at": datetime.now().isoformat()})
        save_json(TODO_FILE, todo_list)
        return f"Added to your todo list: {item}"

    def _list_todo(self) -> str:
        if not todo_list:
            return "Your todo list is empty."
        return "Here are your todos: " + "; ".join(f"{i+1}. {it['item']}" for i, it in enumerate(todo_list))

    def _answer_with_ai(self, prompt: str) -> str:
        # with OpenAI
        if openai and self.openai_key:
            try:
                self.chat_history.append({"role": "user", "content": prompt})
                resp = openai.ChatCompletion.create(
                    model='gpt-4o-mini',
                    messages=[{"role": "system", "content": "You are a friendly helpful AI assistant."}] + self.chat_history,
                    max_tokens=250
                )
                reply = resp['choices'][0]['message']['content'].strip()
                self.chat_history.append({"role": "assistant", "content": reply})
                return reply
            except Exception as e:
                print("OpenAI error:", e)

        # fallback: Wikipedia
        if wikipedia:
            try:
                return wikipedia.summary(prompt, sentences=2)
            except DisambiguationError as e:
                return f"Your query is ambiguous. Try one of these: {', '.join(e.options[:5])}"
            except PageError:
                return "I couldn't find anything on Wikipedia."
            except Exception:
                pass
        return "Sorry, I couldn’t find an answer."

    def run(self):
        self.speaker.say("Hello! I'm your assistant. You can just start talking to me.")
        if not self.listener:
            self.speaker.say("Speech recognition isn't available.")
            return

        while self.running:
            text = self.listener.listen()
            if not text:
                continue
            if text.lower().strip() in ("exit", "quit", "stop", "goodbye"):
                self.speaker.say("Goodbye! Have a great day!")
                self.running = False
                break
            response = self.handle_command(text)
            self.speaker.say(response)

# ---------------- Run ----------------
if __name__ == '__main__':
    assistant = ShreeVoice()
    assistant.run()
