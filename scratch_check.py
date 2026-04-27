import inspect
try:
    from llama_cpp import Llama
    print("Llama init args:")
    for param in inspect.signature(Llama.__init__).parameters:
        print(param)
    print("\ncreate_chat_completion args:")
    for param in inspect.signature(Llama.create_chat_completion).parameters:
        print(param)
except Exception as e:
    print(f"Error: {e}")
