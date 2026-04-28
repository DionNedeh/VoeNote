import gc
import re
from llama_cpp import Llama


class LLMEngine:
    def __init__(self):
        self.llm = None
        self.histories = {"procomm": [], "docintel": [], "codeassist": [], "shared": []}
        self.shared_context = False
        self.thinking_enabled = True
        self.show_thinking = False
        self.system_prompt = "You are a highly capable AI assistant."
        self.stop_flag = False
        self.is_generating = False
        self.model_path = None
        self.model_family = None

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
            self.model_path = model_path
            self.model_family = self._detect_model_family(model_path)
            return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False

    def unload(self):
        self.stop_flag = True
        import time
        for _ in range(20):
            if not getattr(self, "is_generating", False):
                break
            time.sleep(0.1)

        if self.llm is not None:
            del self.llm
            self.llm = None
            for k in self.histories:
                self.histories[k] = []
            gc.collect()

    def clear_history(self, suite="procomm"):
        if self.shared_context:
            self.histories["shared"] = []
        else:
            self.histories[suite] = []

    def get_history(self, suite="procomm"):
        if self.shared_context:
            return self.histories["shared"]
        return self.histories.get(suite, [])

    def set_history(self, history, suite="procomm"):
        if self.shared_context:
            self.histories["shared"] = history
        else:
            self.histories[suite] = history

    def _detect_model_family(self, model_path):
        try:
            lp = (model_path or "").lower()
        except Exception:
            return None

        if "gpt-oss" in lp:
            return "gpt-oss"
        if "nemotron" in lp:
            return "nemotron"
        if "qwen" in lp:
            return "qwen"
        if "gemma" in lp:
            return "gemma"
        return None

    def _should_strip_output(self):
        return (not self.show_thinking) or (not self.thinking_enabled)

    def _uses_system_role(self):
        return self.model_family != "gemma"

    def _add_reasoning_directive(self, user_content):
        if self.model_family in {"qwen", "nemotron"}:
            directive = "/think" if self.thinking_enabled else "/no_think"
            return f"{directive}\n\n{user_content}"
        return user_content

    def _strip_control_markers(self, text):
        if not text:
            return text
        text = re.sub(r"(?is)<\|start\|>assistant", "", text)
        text = re.sub(r"(?is)<\|channel\|>final(?: [^<|]+)?<\|message\|>", "", text)
        text = re.sub(r"(?is)<\|channel\|>commentary(?: [^<|]+)?<\|message\|>", "", text)
        text = re.sub(r"(?is)<\|message\|>", "", text)
        text = re.sub(r"(?is)<\|return\|>", "", text)
        text = re.sub(r"(?is)</final>", "", text)
        text = re.sub(r"(?is)<div[^>]*class=['\"]thinking-process['\"][^>]*>", "", text)
        text = re.sub(r"(?is)</div>", "", text)
        return text

    def _extract_from_final_cues(self, text):
        cue_patterns = [
            r"(?is)(?:thus\s+)?final answer\s*:\s*",
            r"(?is)final response\s*:\s*",
            r"(?is)provide final response\s*:\s*",
            r"(?is)plain text\s*:\s*",
            r"(?is)now respond\.\s*",
        ]
        last_match = None
        for pattern in cue_patterns:
            for match in re.finditer(pattern, text):
                last_match = match

        if last_match is None:
            return text

        suffix = text[last_match.end():].strip()
        if not suffix:
            return text

        lines = [line.strip() for line in suffix.splitlines() if line.strip()]
        if not lines:
            return text

        first_line = lines[0]
        first_line = re.sub(r"^[\[{('\"]+", "", first_line)
        first_line = re.sub(r"[\]})'\" ]+$", "", first_line)
        return first_line or text

    def sanitize_hidden_output(self, text):
        """Best-effort cleanup for hidden reasoning across several model formats."""
        if not text:
            return text

        cleaned = text

        cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
        lower_cleaned = cleaned.lower()
        closing_tag = "</think>"
        if closing_tag in lower_cleaned:
            last_close = lower_cleaned.rfind(closing_tag)
            cleaned = cleaned[last_close + len(closing_tag):]

        cleaned = re.sub(
            r"(?is)<div[^>]*class=['\"]thinking-process['\"][^>]*>.*?</div>",
            "",
            cleaned,
        )
        cleaned = re.sub(r"(?is)<think>.*", "", cleaned)
        cleaned = re.sub(r"(?is)<div[^>]*class=['\"]thinking-process['\"][^>]*>.*", "", cleaned)

        final_markers = [
            "<|start|>assistant<|channel|>final<|message|>",
            "<|start|>assistant<|channel|>final json<|message|>",
            "<|channel|>final<|message|>",
            "<|channel|>final json<|message|>",
        ]
        lower_cleaned = cleaned.lower()
        last_final_idx = -1
        last_final_len = 0
        for marker in final_markers:
            idx = lower_cleaned.rfind(marker.lower())
            if idx > last_final_idx:
                last_final_idx = idx
                last_final_len = len(marker)
        if last_final_idx != -1:
            cleaned = cleaned[last_final_idx + last_final_len:]
        else:
            analysis_marker = "<|channel|>analysis<|message|>"
            analysis_idx = lower_cleaned.find(analysis_marker)
            if analysis_idx != -1:
                end_idx = lower_cleaned.rfind("<|end|>")
                if end_idx > analysis_idx:
                    cleaned = cleaned[end_idx + len("<|end|>"):]
                else:
                    cleaned = re.sub(r"(?is)<\|channel\|>analysis<\|message\|>.*", "", cleaned)

        cleaned = re.sub(r"(?is)<\|channel\|>analysis<\|message\|>.*?(?:<\|end\|>|$)", "", cleaned)
        cleaned = re.sub(r"(?is)<\|channel\|>commentary(?: [^<|]+)?<\|message\|>.*?(?:<\|end\|>|$)", "", cleaned)
        cleaned = self._strip_control_markers(cleaned)
        cleaned = self._extract_from_final_cues(cleaned)
        cleaned = self._strip_control_markers(cleaned)

        return cleaned.strip()

    def strip_thinking_from_text(self, text):
        """Backward-compatible alias used by older callers/tests."""
        return self.sanitize_hidden_output(text)

    def get_history_filtered(self, suite="procomm", show_thinking=None):
        """Return a copy of history with hidden reasoning removed when requested."""
        if show_thinking is None:
            show_thinking = self.show_thinking

        raw = self.get_history(suite)
        if show_thinking:
            return [dict(m) for m in raw]

        filtered = []
        for msg in raw:
            m = dict(msg)
            if m.get("role") == "assistant":
                m["content"] = self.sanitize_hidden_output(m.get("content", ""))
            filtered.append(m)
        return filtered

    def generate_stream(self, suite, text, persona, context, document_text=""):
        self.stop_flag = False
        self.is_generating = True

        if self.llm is None:
            self.is_generating = False
            yield "Error: Engine not loaded."
            return

        sys_prompt = self._get_system_prompt(suite, persona)

        user_content = text
        if context:
            user_content = f"Context/Workspace:\n{context}\n\nQuery:\n{text}"

        if document_text and suite == "docintel":
            user_content = f"Document Snippet:\n{document_text[:100000]}\n\nQuery:\n{text}"

        user_content = self._add_reasoning_directive(user_content)

        active_history = self.histories["shared"] if self.shared_context else self.histories.get(suite, [])
        active_history.append({"role": "user", "content": user_content})

        send_history = self.get_history_filtered(suite, show_thinking=False)
        recent_history = send_history[-5:]

        payload = []
        if self._uses_system_role():
            payload.append({"role": "system", "content": sys_prompt})
            payload.extend(recent_history)
        else:
            system_injected = False
            for msg in recent_history:
                if msg["role"] == "user" and not system_injected:
                    payload.append({"role": "user", "content": f"{sys_prompt}\n\n{msg['content']}"})
                    system_injected = True
                else:
                    payload.append(msg)

        try:
            completion_kwargs = dict(
                messages=payload,
                max_tokens=1024,
                stream=True,
                temperature=0.7,
                top_p=0.8,
                top_k=20,
                min_p=0.0,
                presence_penalty=1.5,
                repeat_penalty=1.0,
            )

            if not self.thinking_enabled:
                logit_bias_map = {}
                try:
                    if hasattr(self.llm, "tokenize"):
                        for marker in ("<think>", "</think>", "<|channel|>analysis<|message|>"):
                            try:
                                toks = self.llm.tokenize(marker.encode("utf-8"))
                                for token in toks:
                                    logit_bias_map[int(token)] = -100
                            except Exception:
                                continue
                except Exception:
                    logit_bias_map = {}

                if logit_bias_map:
                    completion_kwargs["logit_bias"] = logit_bias_map

            try:
                stream = self.llm.create_chat_completion(**completion_kwargs)
            except TypeError:
                if "logit_bias" in completion_kwargs:
                    completion_kwargs.pop("logit_bias", None)
                    stream = self.llm.create_chat_completion(**completion_kwargs)
                else:
                    raise

            if self._should_strip_output():
                raw_response = ""
                for chunk in stream:
                    if getattr(self, "stop_flag", False):
                        raw_response += "\n\n[Generation stopped]"
                        break

                    if "choices" not in chunk or not chunk["choices"]:
                        continue

                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        raw_response += content

                sanitized = self.sanitize_hidden_output(raw_response)
                if "[Generation stopped]" in raw_response:
                    sanitized = (sanitized + "\n\n[Generation stopped]").strip()
                active_history.append({"role": "assistant", "content": sanitized})
                if sanitized:
                    yield sanitized
                return

            full_response = ""
            buffer = ""
            in_thought = False
            think_open = "<think>"
            think_close = "</think>"

            for chunk in stream:
                if getattr(self, "stop_flag", False):
                    full_response += "\n\n[Generation stopped]"
                    break

                if "choices" not in chunk or not chunk["choices"]:
                    continue

                delta = chunk["choices"][0].get("delta", {})
                content = delta.get("content", "")
                if not content:
                    continue

                buffer += content

                while True:
                    lower_buf = buffer.lower()

                    if in_thought:
                        end_idx = lower_buf.find(think_close)
                        if end_idx != -1:
                            thought = buffer[:end_idx]
                            thought_chunk = thought + "</div>\n"
                            full_response += thought_chunk
                            yield thought_chunk
                            buffer = buffer[end_idx + len(think_close):]
                            in_thought = False
                            continue

                        partial_found = False
                        for i in range(1, len(think_close)):
                            if lower_buf.endswith(think_close[:i]):
                                safe_thought = buffer[:-i]
                                if safe_thought:
                                    full_response += safe_thought
                                    yield safe_thought
                                buffer = buffer[-i:]
                                partial_found = True
                                break

                        if not partial_found:
                            if buffer:
                                full_response += buffer
                                yield buffer
                            buffer = ""
                        break

                    start_idx = lower_buf.find(think_open)
                    if start_idx != -1:
                        visible_text = buffer[:start_idx]
                        if visible_text:
                            full_response += visible_text
                            yield visible_text
                        thought_start = "\n<div class='thinking-process'>"
                        full_response += thought_start
                        yield thought_start
                        buffer = buffer[start_idx + len(think_open):]
                        in_thought = True
                        continue

                    partial_found = False
                    for i in range(1, len(think_open)):
                        if lower_buf.endswith(think_open[:i]):
                            safe_text = buffer[:-i]
                            if safe_text:
                                full_response += safe_text
                                yield safe_text
                            buffer = buffer[-i:]
                            partial_found = True
                            break

                    if not partial_found:
                        if buffer:
                            full_response += buffer
                            yield buffer
                        buffer = ""
                    break

            if getattr(self, "stop_flag", False) and not full_response.endswith("\n\n[Generation stopped]"):
                full_response += "\n\n[Generation stopped]"

            if buffer:
                if in_thought:
                    final_chunk = buffer + "</div>\n"
                    full_response += final_chunk
                    yield final_chunk
                else:
                    full_response += buffer
                    yield buffer

            active_history.append({"role": "assistant", "content": full_response})
        except Exception as e:
            yield f"\n[Error: {str(e)}]"
        finally:
            self.is_generating = False

    def _get_system_prompt(self, suite, persona):
        base_instruction = ""
        if suite == "procomm":
            if persona == "resume":
                base_instruction = "You are an expert resume writer and ATS keyword specialist. Provide professional, impactful phrasing."
            elif persona == "grammar":
                base_instruction = "You are a professional copyeditor. Fix grammar and rewrite for clarity and tone."
            elif persona == "email":
                base_instruction = "You are an expert email drafter. Write concise, professional emails."
            elif persona == "translator":
                base_instruction = "You are a master language translator and tutor. Translate text accurately and explain nuances."
            elif persona == "bullet":
                base_instruction = "You are an expert Bullet List Maker. You MUST output your response ONLY as a bulleted list. Extract all key points from the provided text and format them exclusively as bullet points. Do not include any conversational filler."
            else:
                base_instruction = "You are a helpful writing assistant."
        elif suite == "docintel":
            base_instruction = "You are a Document Intelligence AI. Answer questions based on the provided document text accurately and concisely."
        elif suite == "codeassist":
            base_instruction = "You are an expert 10x software engineer and coding tutor. Provide optimized, clean, and well-commented code."
        else:
            base_instruction = self.system_prompt

        base_instruction += " IMPORTANT: DO NOT use any markdown formatting like asterisks (**) or underscores (__) for bolding or italics in your response. Use plain text formatting only."
        if self.thinking_enabled:
            base_instruction += " Think carefully before answering. If the model natively supports hidden reasoning, keep it out of the user-facing answer unless explicitly rendered separately."
        else:
            base_instruction += " Provide only the final answer. Do not output reasoning, chain-of-thought, analysis, commentary, hidden channels, or control tags."
            if self.model_family == "gpt-oss":
                base_instruction += " Respond only with the final user-facing message. Do not emit analysis or commentary channels."
        return base_instruction
