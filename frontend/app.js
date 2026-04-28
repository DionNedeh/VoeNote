// DOM Elements
const navItems = document.querySelectorAll('.nav-item');
const views = document.querySelectorAll('.view');
const viewTitle = document.getElementById('view-title');
const voiceBtn = document.getElementById('voice-btn');
const engineToggleBtn = document.getElementById('engine-toggle-btn');
const sharedCtxBtn = document.getElementById('shared-ctx-btn');
const thinkingToggleBtn = document.getElementById('thinking-toggle-btn');
const engineIndicator = document.getElementById('engine-indicator');
const engineStatusText = document.getElementById('engine-status-text');

// Settings Modal
const settingsModal = document.getElementById('settings-modal');
const openSettingsBtn = document.getElementById('open-settings');
const closeSettingsBtn = document.getElementById('close-settings');
const btnBrowseModel = document.getElementById('btn-browse-model');
const btnSaveSettings = document.getElementById('btn-save-settings');

// State
let engineOnline = false;
let isRecording = false;
let activeView = 'procomm';
let thinkingEnabled = true;

// PyWebView API Reference (will be injected by Python)
let api = null;

window.addEventListener('pywebviewready', () => {
    api = window.pywebview.api;
    console.log("PyWebView API is ready.");
    
    // Initialize thinking toggle state
    api.get_thinking_enabled().then(enabled => {
        thinkingEnabled = enabled;
        updateThinkingToggleUI();
    });
    
    // Initialize show-thinking setting (persisted)
    if(api.get_show_thinking) {
        api.get_show_thinking().then(show => {
            const select = document.getElementById('setting-show-thinking');
            if(select) select.value = show ? 'true' : 'false';
            try { localStorage.setItem('setting-show-thinking', show ? 'true' : 'false'); } catch(e) {}
        }).catch(e => console.warn('get_show_thinking failed', e));
    } else {
        const stored = localStorage.getItem('setting-show-thinking');
        if(stored) {
            const select = document.getElementById('setting-show-thinking');
            if(select) select.value = stored;
        }
    }
});

// View Switching
navItems.forEach(item => {
    item.addEventListener('click', () => {
        navItems.forEach(nav => nav.classList.remove('active'));
        views.forEach(view => view.classList.remove('active'));
        
        item.classList.add('active');
        const viewId = item.getAttribute('data-view');
        document.getElementById(`view-${viewId}`).classList.add('active');
        
        viewTitle.innerText = item.querySelector('span').innerText;
        activeView = viewId;
    });
});

// Thinking Toggle
function updateThinkingToggleUI() {
    if(thinkingEnabled) {
        thinkingToggleBtn.classList.add('active');
        thinkingToggleBtn.classList.remove('disabled');
        thinkingToggleBtn.style.color = '#3b82f6';
    } else {
        thinkingToggleBtn.classList.remove('active');
        thinkingToggleBtn.classList.add('disabled');
        thinkingToggleBtn.style.color = '';
    }
}

thinkingToggleBtn.addEventListener('click', async () => {
    if(!api) return;
    thinkingEnabled = !thinkingEnabled;
    thinkingToggleBtn.disabled = true;
    try {
        await api.toggle_thinking(thinkingEnabled);
    } catch(e) {
        console.warn('toggle_thinking failed', e);
    }
    thinkingToggleBtn.disabled = false;
    updateThinkingToggleUI();
});

// Settings Modal Handlers
openSettingsBtn.addEventListener('click', () => settingsModal.classList.add('active'));
closeSettingsBtn.addEventListener('click', () => settingsModal.classList.remove('active'));

btnBrowseModel.addEventListener('click', async () => {
    if(api) {
        const path = await api.browse_model();
        if(path) document.getElementById('setting-model-path').value = path;
    }
});

btnSaveSettings.addEventListener('click', async () => {
    const path = document.getElementById('setting-model-path').value;
    const ctx = parseInt(document.getElementById('setting-n-ctx').value);
    const gpu = parseInt(document.getElementById('setting-n-gpu').value);
    const showThinking = document.getElementById('setting-show-thinking').value === 'true';
    
    if(!path) {
        alert("Please select a model path.");
        return;
    }
    
    settingsModal.classList.remove('active');
    
    setEngineStatus('loading', 'Loading Model...');
    engineToggleBtn.disabled = true;
    
    if(api) {
        try {
            await api.set_show_thinking(showThinking);
            try { localStorage.setItem('setting-show-thinking', showThinking ? 'true' : 'false'); } catch(e) {}
        } catch(e) {
            console.warn('set_show_thinking failed', e);
        }
        const success = await api.load_model(path, ctx, gpu);
        if(success) {
            setEngineStatus('online', 'Engine Online');
            engineToggleBtn.innerText = "Disconnect Engine";
            engineOnline = true;
            voiceBtn.classList.remove('disabled');
            engineToggleBtn.disabled = false;
        } else {
            setEngineStatus('offline', 'Load Failed');
            engineToggleBtn.innerText = "Connect Engine";
            engineToggleBtn.disabled = false;
        }
    }
});

engineToggleBtn.addEventListener('click', async () => {
    if(!api) return;
    
    if(engineOnline) {
        setEngineStatus('loading', 'Deloading...');
        engineToggleBtn.disabled = true;
        try {
            const success = await api.deload_model();
            if(success) {
                setEngineStatus('offline', 'Engine Offline');
                engineToggleBtn.innerText = "Connect Engine";
                engineOnline = false;
                engineToggleBtn.disabled = false;
                voiceBtn.classList.add('disabled');
            }
        } catch(e) {
            console.error("Deload failed:", e);
            engineToggleBtn.disabled = false;
            setEngineStatus('online', 'Engine Online');
        }
    } else {
        settingsModal.classList.add('active');
    }
});

let sharedContext = false;
sharedCtxBtn.addEventListener('click', async () => {
    if(!api) return;
    sharedContext = !sharedContext;
    await api.toggle_shared_context(sharedContext);
    if(sharedContext) {
        sharedCtxBtn.classList.remove('disabled');
        sharedCtxBtn.classList.add('active');
        sharedCtxBtn.style.color = '#3b82f6';
    } else {
        sharedCtxBtn.classList.remove('active');
        sharedCtxBtn.classList.add('disabled');
        sharedCtxBtn.style.color = '';
    }
});

// Audio Recording
voiceBtn.addEventListener('click', async () => {
    if(!engineOnline || !api) return;
    
    if(isRecording) {
        isRecording = false;
        voiceBtn.classList.remove('recording');
        const transcription = await api.stop_recording();
        if(transcription) appendTranscription(transcription);
    } else {
        const started = await api.start_recording();
        if(started) {
            isRecording = true;
            voiceBtn.classList.add('recording');
        }
    }
});

function appendTranscription(text) {
    if(!text) return;
    
    let targetInput = null;
    if(activeView === 'procomm') targetInput = document.getElementById('procomm-editor');
    else if(activeView === 'docintel') targetInput = document.getElementById('doc-input');
    else if(activeView === 'codeassist') targetInput = document.getElementById('code-input');
    
    if(targetInput) targetInput.value += (targetInput.value ? " " : "") + text;
}

// Chat Sending Logic
async function sendMessage(suite, inputId, historyId) {
    if(!engineOnline || !api) {
        alert("Please connect the engine first.");
        return;
    }
    
    const input = document.getElementById(inputId);
    const text = input.value.trim();
    if(!text) return;
    
    input.value = '';
    
    // UI state toggle
    let btnPrefix = suite;
    if(suite === 'docintel') btnPrefix = 'doc';
    if(suite === 'codeassist') btnPrefix = 'code';
    
    const stopBtn = document.getElementById(btnPrefix + '-stop');
    const sendBtn = document.getElementById(inputId.replace('input', 'send'));
    if(stopBtn) stopBtn.classList.remove('disabled');
    if(sendBtn) sendBtn.disabled = true;
    
    appendMessage(historyId, text, 'user');
    
    let persona = "general";
    let extraContext = "";
    
    if(suite === 'procomm') {
        persona = document.getElementById('procomm-persona').value;
        extraContext = document.getElementById('procomm-editor').value;
    }
    
    const msgId = 'msg-' + Date.now();
    appendMessage(historyId, "...", 'assistant', msgId);
    
    await api.send_message({
        suite: suite,
        text: text,
        persona: persona,
        context: extraContext,
        msg_id: msgId
    });
}

function update_stream(msgId, chunk) {
    const el = document.getElementById(msgId);
    if(el) {
        if(el.innerText === "...") el.innerText = "";
        el.innerText += chunk;
        scrollToBottom(el.parentElement.id);
    }
}

function finalize_stream(msgId, fullTextHtml, rawText) {
    const el = document.getElementById(msgId);
    if(el) {
        el.innerHTML = fullTextHtml;
        
        if (el.classList.contains('assistant')) {
            const actionDiv = document.createElement('div');
            actionDiv.className = 'message-actions';
            
            const copyBtn = document.createElement('button');
            copyBtn.className = 'action-btn small-btn';
            copyBtn.innerText = 'Copy';
            copyBtn.onclick = () => navigator.clipboard.writeText(rawText);
            
            const insertBtn = document.createElement('button');
            insertBtn.className = 'action-btn small-btn';
            insertBtn.innerText = 'Insert';
            insertBtn.onclick = () => {
                const editor = document.getElementById('procomm-editor');
                if(editor) editor.value += (editor.value ? "\n" : "") + rawText;
            };
            
            actionDiv.appendChild(copyBtn);
            actionDiv.appendChild(insertBtn);
            el.appendChild(actionDiv);
        }
        
        scrollToBottom(el.parentElement.id);
        
        // Re-enable send button, disable stop button
        const historyId = el.parentElement.id;
        let suite = 'procomm';
        if(historyId.includes('doc')) suite = 'doc';
        if(historyId.includes('code')) suite = 'code';
        
        const stopBtn = document.getElementById(suite + '-stop');
        let sendBtnId = suite + '-send';
        if(suite === 'procomm') sendBtnId = 'procomm-send';
        const sendBtn = document.getElementById(sendBtnId);
        
        if(stopBtn) stopBtn.classList.add('disabled');
        if(sendBtn) sendBtn.disabled = false;
    }
}

document.getElementById('procomm-send').addEventListener('click', () => sendMessage('procomm', 'procomm-input', 'procomm-chat-history'));
document.getElementById('doc-send').addEventListener('click', () => sendMessage('docintel', 'doc-input', 'doc-chat-history'));
document.getElementById('code-send').addEventListener('click', () => sendMessage('codeassist', 'code-input', 'code-chat-history'));

['procomm', 'doc', 'code'].forEach(suite => {
    const stopBtn = document.getElementById(suite + '-stop');
    if(stopBtn) {
        stopBtn.addEventListener('click', async () => {
            if(api) await api.stop_generation();
        });
    }
});

['procomm-input', 'doc-input', 'code-input'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', (e) => {
        if(e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            document.getElementById(id.replace('input', 'send')).click();
        }
    });
});

// ProComm Notepad & Chat Actions
document.getElementById('procomm-notepad-clear').addEventListener('click', () => {
    document.getElementById('procomm-editor').value = '';
});
document.getElementById('procomm-notepad-load').addEventListener('click', async () => {
    if(api) {
        const text = await api.load_text_file();
        if(text !== null) document.getElementById('procomm-editor').value = text;
    }
});
document.getElementById('procomm-notepad-save').addEventListener('click', async () => {
    if(api) await api.save_text_file(document.getElementById('procomm-editor').value);
});

document.getElementById('procomm-chat-clear').addEventListener('click', () => {
    document.getElementById('procomm-chat-history').innerHTML = '<div class="message system">Welcome to Pro-Comm Suite. Connect the engine to start.</div>';
    if(api) api.clear_chat_history('procomm');
});
document.getElementById('procomm-chat-load').addEventListener('click', async () => {
    if(api) {
        const historyData = await api.load_chat_file('procomm');
        if(historyData && Array.isArray(historyData)) {
            const history = document.getElementById('procomm-chat-history');
            history.innerHTML = '';
            historyData.forEach(msg => {
                if(msg.role !== 'system') appendMessage('procomm-chat-history', msg.content, msg.role === 'user' ? 'user' : 'assistant');
            });
        }
    }
});
document.getElementById('procomm-chat-save').addEventListener('click', async () => {
    if(api) await api.save_chat_file('procomm');
});

document.getElementById('doc-chat-clear').addEventListener('click', () => {
    document.getElementById('doc-chat-history').innerHTML = '<div class="message system">Upload a document to begin chatting with it.</div>';
    if(api) api.clear_chat_history('docintel');
});

document.getElementById('code-chat-clear').addEventListener('click', () => {
    document.getElementById('code-chat-history').innerHTML = '<div class="message system">Code Assistant ready.</div>';
    if(api) api.clear_chat_history('codeassist');
});

// Document Upload Logic
const uploadZone = document.getElementById('doc-upload-zone');
const fileInput = document.getElementById('doc-file-input');
const docInfo = document.getElementById('doc-info');
const docFilename = document.getElementById('doc-filename');
const docTokens = document.getElementById('doc-tokens');
const docClearBtn = document.getElementById('doc-clear-btn');
const docSummarizeBtn = document.getElementById('doc-summarize-btn');

uploadZone.addEventListener('click', (e) => {
    e.preventDefault();
    if(api) {
        api.pick_document().then(fileData => {
            if(fileData && fileData.path) {
                uploadZone.style.display = 'none';
                docInfo.style.display = 'flex';
                docFilename.innerText = fileData.name;
                docTokens.innerText = `~${fileData.tokens} tokens`;
            }
        });
    }
});

docClearBtn.addEventListener('click', async () => {
    if(api) await api.clear_document();
    uploadZone.style.display = 'block';
    docInfo.style.display = 'none';
});

docSummarizeBtn.addEventListener('click', () => {
    const input = document.getElementById('doc-input');
    input.value = "Please provide a concise summary of this document.";
    document.getElementById('doc-send').click();
});

// Helpers
function setEngineStatus(state, text) {
    engineIndicator.className = 'status-indicator ' + state;
    engineStatusText.innerText = text;
}

function appendMessage(historyId, text, role, id=null) {
    const history = document.getElementById(historyId);
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if(id) div.id = id;
    
    if(role === 'assistant') {
        // Just text initially, will be replaced by finalize_stream
        div.innerText = text;
    } else {
        div.innerText = text;
    }
    
    history.appendChild(div);
    scrollToBottom(historyId);
}

function scrollToBottom(historyId) {
    const history = document.getElementById(historyId);
    history.scrollTop = history.scrollHeight;
}
