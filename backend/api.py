import os
import json
import threading
from backend.engine import LLMEngine
from backend.audio import AudioRecorder
from backend.document import DocumentProcessor
import webview
try:
    import markdown
except ImportError:
    markdown = None

class AppAPI:
    def __init__(self):
        self._window = None
        self._engine = LLMEngine()
        self._audio = AudioRecorder()
        self._doc_processor = DocumentProcessor()
        self._current_document = ""

    def set_window(self, window):
        self._window = window

    def browse_model(self):
        file_types = ('GGUF Files (*.gguf)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            return result[0]
        return None

    def load_model(self, path, ctx, gpu):
        return self._engine.load(path, ctx, gpu)

    def deload_model(self):
        self._engine.unload()
        return True

    def toggle_shared_context(self, enabled):
        self._engine.shared_context = enabled
        return True

    def toggle_thinking(self, enabled):
        self._engine.thinking_enabled = enabled
        if getattr(self._engine, 'is_generating', False):
            print("toggle_thinking: changed during generation; engine will apply change immediately for remaining chunks.")
        return True

    def get_thinking_enabled(self):
        return self._engine.thinking_enabled

    def get_show_thinking(self):
        return self._engine.show_thinking

    def set_show_thinking(self, enabled):
        self._engine.show_thinking = enabled
        return True

    def stop_generation(self):
        self._engine.stop_flag = True
        return True

    def start_recording(self):
        return self._audio.start()

    def stop_recording(self):
        return self._audio.stop_and_transcribe()

    def pick_document(self):
        file_types = ('Documents (*.pdf;*.docx;*.txt)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            path = result[0]
            name = os.path.basename(path)
            text, tokens = self._doc_processor.process(path, self._engine)
            self._current_document = text
            return {"path": path, "name": name, "tokens": tokens}
        return None

    def clear_document(self):
        self._current_document = ""
        return True

    def send_message(self, data):
        suite = data.get('suite')
        text = data.get('text')
        persona = data.get('persona', 'general')
        context = data.get('context', '')
        msg_id = data.get('msg_id')
        
        threading.Thread(target=self._process_message, args=(suite, text, persona, context, msg_id), daemon=True).start()
        return True

    def _process_message(self, suite, text, persona, context, msg_id):
        full_text = ""
        for chunk in self._engine.generate_stream(suite, text, persona, context, self._current_document):
            chunk = chunk.replace("*", "").replace("_", "")
            full_text += chunk
            safe_chunk = chunk.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("\n", "\\n").replace('"', '\\"')
            if self._window:
                self._window.evaluate_js(f'update_stream("{msg_id}", "{safe_chunk}");')
        
        html = full_text
        if markdown:
            html = markdown.markdown(full_text, extensions=['fenced_code', 'tables'])
        
        safe_html = html.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("\n", "\\n").replace('"', '\\"')
        safe_raw = full_text.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$").replace("\n", "\\n").replace('"', '\\"')
        
        if self._window:
            self._window.evaluate_js(f'finalize_stream("{msg_id}", "{safe_html}", "{safe_raw}");')

    # Notepad & Chat Actions
    def load_text_file(self):
        file_types = ('Text Files (*.txt;*.md)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            try:
                with open(result[0], 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading file: {e}")
        return None

    def save_text_file(self, content):
        file_types = ('Text Files (*.txt)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename='note.txt', file_types=file_types)
        if result:
            try:
                with open(result, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            except Exception as e:
                print(f"Error saving file: {e}")
        return False

    def clear_chat_history(self, suite="procomm"):
        self._engine.clear_history(suite)
        return True

    def load_chat_file(self, suite="procomm"):
        file_types = ('JSON Files (*.json)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
        if result and len(result) > 0:
            try:
                with open(result[0], 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    self._engine.set_history(history, suite)
                    return history
            except Exception as e:
                print(f"Error loading chat: {e}")
        return None

    def save_chat_file(self, suite="procomm"):
        file_types = ('JSON Files (*.json)', 'All files (*.*)')
        result = self._window.create_file_dialog(webview.SAVE_DIALOG, save_filename='chat_history.json', file_types=file_types)
        if result:
            try:
                with open(result, 'w', encoding='utf-8') as f:
                    json.dump(self._engine.get_history(suite), f, indent=4)
                return True
            except Exception as e:
                print(f"Error saving chat: {e}")
        return False
