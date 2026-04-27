import os
try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import docx
except ImportError:
    docx = None

class DocumentProcessor:
    def process(self, path, engine=None):
        if not os.path.exists(path):
            return "", 0

        ext = path.lower().split('.')[-1]
        text = ""

        if ext == 'pdf' and fitz:
            try:
                doc = fitz.open(path)
                for page in doc:
                    text += page.get_text() + "\n"
            except Exception as e:
                text = f"Error reading PDF: {e}"
                
        elif ext == 'docx' and docx:
            try:
                doc = docx.Document(path)
                text = "\n".join([p.text for p in doc.paragraphs])
            except Exception as e:
                text = f"Error reading DOCX: {e}"
                
        elif ext in ['txt', 'md', 'csv']:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    text = f.read()
            except Exception as e:
                text = f"Error reading text file: {e}"
        else:
            text = "Unsupported file format."

        # Estimate tokens roughly
        tokens = len(text) // 4
        
        # We can ask the engine for exact tokens if loaded, but rough is fine for UI
        if engine and engine.llm:
            try:
                tokens = len(engine.llm.tokenize(text.encode("utf-8")))
            except:
                pass
                
        return text, tokens
