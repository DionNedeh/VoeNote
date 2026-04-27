import gc
from llama_cpp import Llama

class LLMEngine:
    def __init__(self):
        self.llm = None
        self.histories = {"procomm": [], "docintel": [], "codeassist": [], "shared": []}
        self.shared_context = False
        self.system_prompt = "You are a highly capable AI assistant."
        self.stop_flag = False
        self.is_generating = False

    def load(self, model_path, n_ctx=131072, n_gpu_layers=-1):
        try:
            if self.llm is not None:
                self.unload()
                
            self.llm = Llama(
                model_path=model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                verbose=False
            )
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

    def unload(self):
        self.stop_flag = True
        import time
        # Prevent deadlock by waiting for generator to exit
        for _ in range(20):
            if not getattr(self, 'is_generating', False):
                break
            time.sleep(0.1)
            
        if self.llm is not None:
            del self.llm
            self.llm = None
            for k in self.histories:
                self.histories[k] = []
            import gc
            gc.collect()

    def clear_history(self, suite="procomm"):
        if self.shared_context:
            self.histories["shared"] = []
        else:
            self.histories[suite] = []

    def get_history(self, suite="procomm"):
        if self.shared_context: return self.histories["shared"]
        return self.histories.get(suite, [])

    def set_history(self, history, suite="procomm"):
        if self.shared_context:
            self.histories["shared"] = history
        else:
            self.histories[suite] = history

    def generate_stream(self, suite, text, persona, context, document_text=""):
        self.stop_flag = False
        self.is_generating = True
        if self.llm is None:
            self.is_generating = False
            yield "Error: Engine not loaded."
            return

        # Prepare messages based on suite
        sys_prompt = self._get_system_prompt(suite, persona)
        
        user_content = text
        if context:
            user_content = f"Context/Workspace:\n{context}\n\nQuery:\n{text}"
            
        if document_text and suite == "docintel":
            user_content = f"Document Snippet:\n{document_text[:100000]}\n\nQuery:\n{text}"
            
        active_history = self.histories["shared"] if self.shared_context else self.histories.get(suite, [])
        active_history.append({"role": "user", "content": user_content})
        
        # Keep last 5 turns
        recent_history = active_history[-5:]
        
        # Merge system prompt into the very first user message for Gemma compatibility
        payload = []
        system_injected = False
        for msg in recent_history:
            if msg["role"] == "user" and not system_injected:
                payload.append({"role": "user", "content": f"{sys_prompt}\n\n{msg['content']}"})
                system_injected = True
            else:
                payload.append(msg)
                
        try:
            stream = self.llm.create_chat_completion(
                messages=payload,
                max_tokens=1024,
                stream=True,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
                min_p=0.0,
                presence_penalty=1.5,
                repeat_penalty=1.0
            )
            full_response = ""
            in_thought = False
            for chunk in stream:
                if getattr(self, 'stop_flag', False):
                    full_response += "\n\n[Generation stopped]"
                    break
                if 'choices' in chunk and len(chunk['choices']) > 0:
                    delta = chunk['choices'][0].get('delta', {})
                    content = delta.get('content', '')
                    
                    if not content:
                        continue
                        
                    # Handle thinking tags properly
                    if "<think>" in content:
                        in_thought = True
                        content = content.split("<think>")[0]
                        
                    if "</think>" in content:
                        in_thought = False
                        parts = content.split("</think>")
                        content = parts[1] if len(parts) > 1 else ""
                        
                    if in_thought:
                        continue
                        
                    if content:
                        full_response += content
                        yield content
                        
            active_history.append({"role": "assistant", "content": full_response})
        except Exception as e:
            yield f"\n[Error: {str(e)}]"
        finally:
            self.is_generating = False

    def _get_system_prompt(self, suite, persona):
        base_instruction = ""
        if suite == "procomm":
            if persona == "resume": base_instruction = "You are an expert resume writer and ATS keyword specialist. Provide professional, impactful phrasing."
            elif persona == "grammar": base_instruction = "You are a professional copyeditor. Fix grammar and rewrite for clarity and tone."
            elif persona == "email": base_instruction = "You are an expert email drafter. Write concise, professional emails."
            elif persona == "translator": base_instruction = "You are a master language translator and tutor. Translate text accurately and explain nuances."
            elif persona == "bullet": base_instruction = "You are an expert Bullet List Maker. You MUST output your response ONLY as a bulleted list. Extract all key points from the provided text and format them exclusively as bullet points. Do not include any conversational filler."
            else: base_instruction = "You are a helpful writing assistant."
        elif suite == "docintel":
            base_instruction = "You are a Document Intelligence AI. Answer questions based on the provided document text accurately and concisely."
        elif suite == "codeassist":
            base_instruction = "You are an expert 10x software engineer and coding tutor. Provide optimized, clean, and well-commented code."
        else:
            base_instruction = self.system_prompt
            
        return base_instruction + " IMPORTANT: DO NOT use any markdown formatting like asterisks (**) or underscores (__) for bolding or italics in your response. Use plain text formatting only."
