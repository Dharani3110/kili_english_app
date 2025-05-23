import sys
import asyncio
import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write
from pydub import AudioSegment
import tempfile
import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QLabel, QTextEdit, QLineEdit, QTabWidget
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
import json

from qasync import QEventLoop
import gen_ai_apis

auth_key = "openai_auth_key.txt"
system_audio = "output/system_audio.mp3"
user_audio = "output/user_audio.mp3"
feedback_json = "output/feedback.json"
quiz_json = "output/quiz.json"
conversation_txt = "output/conversation.txt"
db_file = "database/english_learnings.db"

# Recording Thread
class RecorderThread(QThread):
    finished = pyqtSignal()

    def __init__(self, samplerate=44100):
        super().__init__()
        self.samplerate = samplerate
        self.recording = []
        self.running = False

    def run(self):
        self.running = True
        with sd.InputStream(samplerate=self.samplerate, channels=1, callback=self.callback):
            while self.running:
                sd.sleep(100)
        self.finished.emit()

    def callback(self, indata, frames, time, status):
        if self.running:
            self.recording.append(indata.copy())

    def stop(self):
        self.running = False

    def save_to_mp3(self):
        audio = np.concatenate(self.recording, axis=0)
        temp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_wav.close()
        write(temp_wav.name, self.samplerate, audio)
        sound = AudioSegment.from_wav(temp_wav.name)
        sound.export(user_audio, format="mp3")
        os.remove(temp_wav.name)
        return user_audio


# Main Application
class EnglishTutorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kili - English Learning App")
        self.recorder_thread = None
        self.qa_pairs = []
        self.current_index = 0
        self.showing_question = True
        self.system_audio_enabled = True
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        tab_widget = QTabWidget()

        # === Tab 1: Chat ===
        chat_tab = QWidget()
        chat_layout = QVBoxLayout()

        # Toggle buttons
        toggle_layout = QHBoxLayout()
        self.toggle_audio = QPushButton("🔊 System Audio")
        self.toggle_audio.setCheckable(True)
        self.toggle_audio.setChecked(True)
        self.toggle_audio.toggled.connect(lambda checked: setattr(self, "system_audio_enabled", checked))

        # self.toggle_hints = QPushButton("💡 Hints")
        # self.toggle_hints.setCheckable(True)

        toggle_layout.addWidget(self.toggle_audio)
        # toggle_layout.addWidget(self.toggle_hints)
        chat_layout.addLayout(toggle_layout)

        self.chat_display = QTextEdit(readOnly=True)
        self.chat_display.setStyleSheet("font-size: 16px; background-color: #fffbe6; border: 2px solid #f0ad4e; border-radius: 10px; padding: 10px;")
        chat_layout.addWidget(self.chat_display)

        # Chat buttons
        btn_layout = QHBoxLayout()
        self.record_btn = QPushButton("Record", checkable=True)
        self.record_btn.toggled.connect(self.toggle_recording)
        self.clear_chat_btn = QPushButton("Clear chat")
        self.clear_chat_btn.clicked.connect(self.chat_display.clear)
        self.del_history_btn = QPushButton("Delete History")
        self.del_history_btn.clicked.connect(gen_ai_apis.delete_chat_history)

        btn_layout.addWidget(self.record_btn)
        btn_layout.addWidget(self.clear_chat_btn)
        btn_layout.addWidget(self.del_history_btn)
        chat_layout.addLayout(btn_layout)

        msg_layout = QHBoxLayout()
        self.msg_input = QLineEdit()
        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(lambda: asyncio.create_task(self.send_text_message()))
        msg_layout.addWidget(self.msg_input)
        msg_layout.addWidget(self.send_btn)

        chat_layout.addLayout(msg_layout)
        chat_tab.setLayout(chat_layout)

        # === Tab 2: Report ===
        report_tab = QWidget()
        report_layout = QVBoxLayout()

        report_header = QHBoxLayout()
        report_title = QLabel("<b>Conversation Report and Storage</b>")
        self.gen_btn = QPushButton("Generate")
        self.gen_btn.clicked.connect(self.get_report)
        self.feedback_btn = QPushButton("View Feedback")
        self.feedback_btn.clicked.connect(self.show_feedback)
        self.clear_all_btn = QPushButton("Clear")
        self.clear_all_btn.clicked.connect(self.clear_report)

        report_header.addWidget(report_title)
        report_header.addStretch()
        report_header.addWidget(self.gen_btn)
        report_header.addWidget(self.feedback_btn)
        report_header.addWidget(self.clear_all_btn)

        # Input for new memory
        memory_layout = QHBoxLayout()
        self.memory_input = QLineEdit()
        self.memory_dropdown = QComboBox()
        self.memory_dropdown.addItems(["New Word", "New Phrase"])
        self.remember_btn = QPushButton("Remember")
        memory_layout.addWidget(self.memory_input)
        memory_layout.addWidget(self.memory_dropdown)
        memory_layout.addWidget(self.remember_btn)

        # Three section text areas with labels
        self.grammar_text = QTextEdit(readOnly=True)
        self.grammar_text.setStyleSheet("font-size: 16px; background-color: #fffbe6; border: 2px solid #f0ad4e; border-radius: 10px; padding: 10px;")

        self.vocab_text = QTextEdit(readOnly=True)
        self.vocab_text.setStyleSheet("font-size: 16px; background-color: #fffbe6; border: 2px solid #f0ad4e; border-radius: 10px; padding: 10px;")

        self.phrase_text = QTextEdit(readOnly=True)
        self.phrase_text.setStyleSheet("font-size: 16px; background-color: #fffbe6; border: 2px solid #f0ad4e; border-radius: 10px; padding: 10px;")

        # Add all widgets to layout
        report_layout.addLayout(report_header)
        report_layout.addWidget(QLabel("📝 Grammar"))
        report_layout.addWidget(self.grammar_text)
        report_layout.addWidget(QLabel("📚 Vocabulary"))
        report_layout.addWidget(self.vocab_text)
        report_layout.addWidget(QLabel("💬 Phrases"))
        report_layout.addWidget(self.phrase_text)
        report_layout.addLayout(memory_layout)
        
        report_tab.setLayout(report_layout)

        # === Tab 3: Quiz ===
        quiz_tab = QWidget()
        quiz_layout = QVBoxLayout()

        quiz_header = QHBoxLayout()
        quiz_title = QLabel("<b>Quiz Generator</b>")
        self.quiz_btn = QPushButton("Generate")
        self.quiz_btn.clicked.connect(self.generate_quiz)
        self.start_quiz_btn = QPushButton("Start Quiz")
        self.start_quiz_btn.clicked.connect(self.start_quiz)

        quiz_header.addWidget(quiz_title)
        quiz_header.addStretch()
        quiz_header.addWidget(self.quiz_btn)
        quiz_header.addWidget(self.start_quiz_btn)

        self.quiz_display = QTextEdit(readOnly=True)
        self.quiz_display.setStyleSheet("font-size: 16px; background-color: #fffbe6; border: 2px solid #f0ad4e; border-radius: 10px; padding: 10px;")

        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("Previous")
        self.prev_btn.clicked.connect(self.prev_flashcard)
        self.prev_btn.setEnabled(False)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(self.next_flashcard)
        self.next_btn.setEnabled(False)

        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)

        quiz_layout.addLayout(quiz_header)
        quiz_layout.addWidget(self.quiz_display)
        quiz_layout.addLayout(nav_layout)
        quiz_tab.setLayout(quiz_layout)

        # Add tabs
        tab_widget.addTab(chat_tab, "🗨️ Chat")
        tab_widget.addTab(report_tab, "📄 Report")
        tab_widget.addTab(quiz_tab, "🧠 Quiz")

        main_layout.addWidget(tab_widget)
        self.setLayout(main_layout)

    def toggle_recording(self, checked):
        self.record_btn.setText("Stop" if checked else "Record")
        if checked:
            self.start_recording()
        else:
            self.stop_recording()

    def start_recording(self):
        print("[System] Recording started...")
        self.recorder_thread = RecorderThread()
        self.recorder_thread.finished.connect(lambda: asyncio.create_task(self.on_recording_finished()))
        self.recorder_thread.start()

    def stop_recording(self):
        if self.recorder_thread:
            self.recorder_thread.stop()

    def del_audio(self):
        if hasattr(self, "audio_player"):
            self.audio_player.stop()
            self.audio_player.setMedia(QMediaContent())
            self.audio_player.deleteLater()
            del self.audio_player

    def play_audio(self):
        self.audio_player = QMediaPlayer()
        self.audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(system_audio)))
        self.audio_player.play()

    async def send_and_receive_response(self, user_text):
        self.del_audio()
        self.display_message(user_text, "You")

        system_reply = await asyncio.to_thread(gen_ai_apis.conversation_builder, user_text)
        if self.system_audio_enabled:
            await asyncio.to_thread(gen_ai_apis.text_to_speech, system_reply)
            await asyncio.to_thread(self.play_audio)

        self.display_message(system_reply, "System")

    async def on_recording_finished(self):
        path = await asyncio.to_thread(self.recorder_thread.save_to_mp3)
        print(f"[System] Audio saved to: {path}")
        user_text = await asyncio.to_thread(gen_ai_apis.speech_to_text)
        await self.send_and_receive_response(user_text)

    def display_message(self, text=None, sender="You"):
        if text.strip():
            sender = "🤖" if sender == "System" else "👩🏽"
            self.chat_display.append(f"{sender}: {text}\n")
        self.msg_input.clear()
    
    async def send_text_message(self):
        user_text = self.msg_input.text()
        await self.send_and_receive_response(user_text)


    def get_report(self):
        gen_ai_apis.conversation_corrector()

    def show_feedback(self):
        with open(feedback_json, "r") as file:
            feedback = json.load(file)

        # Format Grammar: original + bold correction
        grammar_entries = [
            f"{mistake}<br><b>{correction}</b><br>"
            for mistake, correction in feedback.get("grammar_mistakes", {}).items()
        ]
        grammar_html = "<br>".join(grammar_entries)

        # Format Vocabulary: original + bold suggestion
        vocab_entries = [
            f"{word}<br><b>{suggestion}</b><br>"
            for word, suggestion in feedback.get("better_vocabulary", {}).items()
        ]
        vocab_html = "<br>".join(vocab_entries)

        # Format Phrases: original + bold rewrite
        phrase_entries = [
            f"{phrase}<br><b>{improved}</b><br>"
            for phrase, improved in feedback.get("better_phrases", {}).items()
        ]
        phrase_html = "<br>".join(phrase_entries)

        # Set all outputs
        self.grammar_text.setHtml(grammar_html)
        self.vocab_text.setHtml(vocab_html)
        self.phrase_text.setHtml(phrase_html)

    def clear_report(self):
        self.grammar_text.clear()
        self.vocab_text.clear()
        self.phrase_text.clear()

    def generate_quiz(self):
        gen_ai_apis.create_quiz()

    def start_quiz(self):
        try:
            with open(quiz_json, "r") as infile:
                self.qa_pairs = json.load(infile)
        except Exception:
            self.qa_pairs = []

        if not self.qa_pairs:
            self.quiz_display.setPlainText("No quiz content found.")
            return

        self.current_index = 0
        self.showing_question = True
        self.next_btn.setEnabled(True)
        self.prev_btn.setEnabled(False)
        self.show_flashcard()

    def show_flashcard(self):
        q = self.qa_pairs[self.current_index]["question"]
        a = self.qa_pairs[self.current_index]["answer"]
        if self.showing_question:
            self.quiz_display.setHtml(f"<b>Question:</b><br>{q}")
        else:
            self.quiz_display.setHtml(f"<b>Question:</b><br>{q}<br><br><b>Answer:</b><br>{a}")

    def next_flashcard(self):
        if self.showing_question:
            self.showing_question = False
        else:
            self.showing_question = True
            self.current_index += 1
            if self.current_index >= len(self.qa_pairs):
                self.quiz_display.setHtml('<div style="color: green;"><b>🎉 End of Quiz!</b></div>')
                self.next_btn.setEnabled(False)
                return
        self.prev_btn.setEnabled(self.current_index > 0)
        self.show_flashcard()

    def prev_flashcard(self):
        if self.showing_question:
            self.current_index = max(0, self.current_index - 1)
        self.showing_question = True
        self.prev_btn.setEnabled(self.current_index > 0)
        self.next_btn.setEnabled(True)
        self.show_flashcard()


# Run app with qasync event loop
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("images/kili_logo.png"))
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = EnglishTutorApp()
    window.resize(600, 700)
    window.show()
    gen_ai_apis.init_openai_client(auth_key, system_audio, user_audio, feedback_json, quiz_json, conversation_txt)

    with loop:
        loop.run_forever()
