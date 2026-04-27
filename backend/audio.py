import threading
import tempfile
import os
try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from faster_whisper import WhisperModel
except ImportError:
    np = None
    sd = None
    sf = None
    WhisperModel = None

class AudioRecorder:
    def __init__(self):
        self.is_recording = False
        self.frames = []
        self.sample_rate = 16000
        self.stream = None
        self.model = None

    def start(self):
        if not all([np, sd, sf, WhisperModel]):
            print("Audio dependencies not installed.")
            return False

        if self.is_recording:
            return False

        if self.model is None:
            # Load tiny model for fast transcription
            self.model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

        self.frames = []
        self.is_recording = True
        
        def callback(indata, frames, time, status):
            if status:
                print(status)
            self.frames.append(indata.copy())

        self.stream = sd.InputStream(samplerate=self.sample_rate, channels=1, callback=callback)
        self.stream.start()
        return True

    def stop_and_transcribe(self):
        if not self.is_recording:
            return ""

        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        if not self.frames:
            return ""

        audio_data = np.concatenate(self.frames, axis=0)
        
        # Save to temp file because faster-whisper prefers files or specific arrays
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        try:
            sf.write(temp_path, audio_data, self.sample_rate)
            
            segments, _ = self.model.transcribe(temp_path, language="en")
            text = " ".join([seg.text for seg in segments]).strip()
            return text
        except Exception as e:
            print(f"Transcription error: {e}")
            return ""
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
