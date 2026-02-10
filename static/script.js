// 全局变量
let currentModel = '';
let sessionId = 'session_' + Date.now();
let isLoading = false;

// DOM元素
const modelSelect = document.getElementById('model-select');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const clearBtn = document.getElementById('clear-btn');
const chatMessages = document.getElementById('chat-messages');

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    loadModels();
    setupEventListeners();
    autoResizeTextarea();
});

// 获取API URL
function getApiUrl(endpoint) {
    const baseUrl = window.API_CONFIG?.BASE_URL || window.location.origin;
    let apiEndpoint;
    
    if (window.API_CONFIG?.ENDPOINTS?.[endpoint]) {
        apiEndpoint = window.API_CONFIG.ENDPOINTS[endpoint];
    } else {
        // 默认端点映射
        const endpointMap = {
            'MODELS': '/api/models',
            'CHAT': '/api/chat',
            'CLEAR': '/api/clear',
            'PROCESS_SELECTION': '/api/process-selection'
        };
        apiEndpoint = endpointMap[endpoint] || `/api/${endpoint.toLowerCase()}`;
    }
    
    // 如果baseUrl已经包含路径，直接拼接
    if (apiEndpoint.startsWith('/')) {
        return `${baseUrl}${apiEndpoint}`;
    } else {
        return `${baseUrl}/${apiEndpoint}`;
    }
}

// 加载可用模型
async function loadModels() {
    try {
        const response = await fetch(getApiUrl('MODELS'));
        const data = await response.json();
        
        // 调试信息：打印API返回的数据
        console.log('API返回的模型列表:', data);
        console.log('模型数量:', data.models?.length || 0);
        
        modelSelect.innerHTML = '';
        
        if (data.models.length === 0) {
            modelSelect.innerHTML = '<option value="">无可用模型</option>';
            return;
        }
        
        // 添加模型选项
        data.models.forEach(model => {
            console.log('添加模型:', model.id, model.name);
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.name + (model.available ? '' : ' (未配置)');
            option.disabled = !model.available;
            modelSelect.appendChild(option);
        });
        
        console.log('下拉框选项数量:', modelSelect.options.length);
        
        // 选择第一个可用模型
        const firstAvailable = data.models.find(m => m.available);
        if (firstAvailable) {
            modelSelect.value = firstAvailable.id;
            currentModel = firstAvailable.id;
        }
    } catch (error) {
        console.error('加载模型失败:', error);
        showError('加载模型列表失败，请检查后端服务是否正常运行');
    }
}

// 设置事件监听器
function setupEventListeners() {
    // 模型选择变化
    modelSelect.addEventListener('change', (e) => {
        currentModel = e.target.value;
        if (currentModel) {
            addSystemMessage(`已切换到 ${modelSelect.options[modelSelect.selectedIndex].textContent}`);
        }
    });
    
    // 发送按钮
    sendBtn.addEventListener('click', sendMessage);
    
    // 清空按钮
    clearBtn.addEventListener('click', clearChat);
    
    // 回车发送（Shift+Enter换行）
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// 自动调整文本框高度
function autoResizeTextarea() {
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = messageInput.scrollHeight + 'px';
    });
}

// 发送消息
async function sendMessage() {
    const message = messageInput.value.trim();
    
    if (!message) {
        return;
    }
    
    if (!currentModel) {
        showError('请先选择一个模型');
        return;
    }
    
    if (isLoading) {
        return;
    }
    
    // 添加用户消息到界面
    addMessage('user', message);
    
    // 清空输入框
    messageInput.value = '';
    messageInput.style.height = 'auto';
    
    // 显示加载动画
    showLoading();
    isLoading = true;
    sendBtn.disabled = true;
    
    try {
        const response = await fetch(getApiUrl('CHAT'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                model: currentModel,
                session_id: sessionId
            })
        });
        
        // 检查响应状态
        if (!response.ok) {
            let errorMsg = `请求失败 (${response.status})`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorMsg;
            } catch (e) {
                errorMsg = `服务器错误 (${response.status} ${response.statusText})`;
            }
            throw new Error(errorMsg);
        }
        
        const data = await response.json();
        
        // 检查是否需要用户选择
        if (data.requires_selection) {
            hideLoading();
            showSelectionDialog(data);
            return;
        }
        
        // 如果有进度信息，先显示进度
        if (data.progress && data.progress.length > 0) {
            showProgress(data.progress);
            // 等待一小段时间让用户看到进度
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        
        // 移除加载动画/进度显示
        hideLoading();
        
        // 添加助手回复（优先使用models数组，如果没有则使用model）
        addMessage('assistant', data.response, data.models || (data.model ? [data.model] : null));
        
    } catch (error) {
        console.error('发送消息失败:', error);
        hideLoading();
        
        // 更详细的错误信息
        let errorMessage = '发送消息失败';
        if (error.message) {
            errorMessage += ': ' + error.message;
        } else if (error.name === 'TypeError' && error.message.includes('fetch')) {
            errorMessage = '无法连接到服务器，请检查后端服务是否正常运行';
        } else if (error.name === 'NetworkError' || error.message.includes('network')) {
            errorMessage = '网络连接失败，请检查网络连接';
        } else {
            errorMessage += ': ' + (error.toString() || '未知错误');
        }
        
        showError(errorMessage);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

// 添加消息到聊天界面
function addMessage(role, content, models = null) {
    // 移除欢迎消息
    const welcomeMsg = chatMessages.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // 处理换行
    const formattedContent = content.replace(/\n/g, '<br>');
    contentDiv.innerHTML = formattedContent;
    
    // 如果是助手消息，显示使用的模型和复制按钮
    if (role === 'assistant') {
        // 模型标签
        if (models && models.length > 0) {
            const modelLabel = document.createElement('div');
            modelLabel.className = 'message-model';
            const modelNames = {
                'deepseek-chat': 'DeepSeek Chat',
                'deepseek-reasoner': 'DeepSeek Reasoner'
            };
            // 显示所有模型，用逗号分隔
            const modelDisplayNames = models.map(m => modelNames[m] || m);
            modelLabel.textContent = `使用模型: ${modelDisplayNames.join('、')}`;
            contentDiv.appendChild(modelLabel);
        }
        
        // 复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn';
        copyBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="#999" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="6" width="8" height="8" rx="1"></rect>
            <rect x="4" y="4" width="8" height="8" rx="1" fill="#fff"></rect>
        </svg>`;
        copyBtn.title = '复制内容';
        copyBtn.onclick = () => {
            copyToClipboard(content, copyBtn);
        };
        contentDiv.appendChild(copyBtn);
    }
    
    messageDiv.appendChild(contentDiv);
    
    chatMessages.appendChild(messageDiv);
    
    // 滚动到底部
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 复制内容到剪贴板
function copyToClipboard(text, button) {
    // 移除HTML标签，只保留纯文本
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = text;
    const plainText = tempDiv.textContent || tempDiv.innerText || text;
    
    // 使用现代 Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(plainText).then(() => {
            // 复制成功，更新按钮状态
            const svg = button.querySelector('svg');
            if (svg) {
                svg.style.stroke = '#ffffff';
            }
            button.style.background = '#4caf50';
            
            setTimeout(() => {
                const svg = button.querySelector('svg');
                if (svg) {
                    svg.style.stroke = '';
                }
                button.style.background = '';
            }, 2000);
        }).catch(err => {
            console.error('复制失败:', err);
            showError('复制失败，请手动复制');
        });
    } else {
        // 降级方案：使用传统方法
        const textArea = document.createElement('textarea');
        textArea.value = plainText;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        
        try {
            document.execCommand('copy');
            const svg = button.querySelector('svg');
            if (svg) {
                svg.style.stroke = '#ffffff';
            }
            button.style.background = '#4caf50';
            
            setTimeout(() => {
                const svg = button.querySelector('svg');
                if (svg) {
                    svg.style.stroke = '';
                }
                button.style.background = '';
            }, 2000);
        } catch (err) {
            console.error('复制失败:', err);
            showError('复制失败，请手动复制');
        } finally {
            document.body.removeChild(textArea);
        }
    }
}

// 添加系统消息
function addSystemMessage(content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message system';
    messageDiv.style.justifyContent = 'center';
    messageDiv.style.margin = '10px 0';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.style.background = '#e3f2fd';
    contentDiv.style.color = '#1976d2';
    contentDiv.style.fontSize = '13px';
    contentDiv.style.padding = '8px 12px';
    contentDiv.textContent = content;
    
    messageDiv.appendChild(contentDiv);
    chatMessages.appendChild(messageDiv);
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 显示加载动画
function showLoading() {
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message assistant';
    loadingDiv.id = 'loading-message';
    
    const loading = document.createElement('div');
    loading.className = 'message-content loading';
    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('div');
        dot.className = 'loading-dot';
        loading.appendChild(dot);
    }
    
    loadingDiv.appendChild(loading);
    chatMessages.appendChild(loadingDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 显示进度信息
function showProgress(progressSteps) {
    const loadingMsg = document.getElementById('loading-message');
    if (!loadingMsg) return;
    
    const progressContainer = document.createElement('div');
    progressContainer.className = 'progress-container';
    
    progressSteps.forEach((step, index) => {
        const progressItem = document.createElement('div');
        progressItem.className = 'progress-item';
        progressItem.textContent = step;
        
        // 根据步骤类型设置样式
        if (step.startsWith('✅')) {
            progressItem.classList.add('progress-completed');
        } else if (step.startsWith('🔍')) {
            progressItem.classList.add('progress-processing');
        }
        
        progressContainer.appendChild(progressItem);
    });
    
    // 替换加载动画为进度显示
    const loadingContent = loadingMsg.querySelector('.loading');
    if (loadingContent) {
        loadingContent.innerHTML = '';
        loadingContent.appendChild(progressContainer);
        loadingContent.classList.remove('loading');
        loadingContent.classList.add('progress-content');
    }
}

// 隐藏加载动画
function hideLoading() {
    const loadingMsg = document.getElementById('loading-message');
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

// 显示选择对话框
function showSelectionDialog(data) {
    const selectionDiv = document.createElement('div');
    selectionDiv.className = 'message assistant';
    selectionDiv.id = 'selection-message';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content selection-content';
    
    // 标题
    const title = document.createElement('div');
    title.style.fontWeight = 'bold';
    title.style.marginBottom = '15px';
    title.style.fontSize = '16px';
    title.textContent = data.prompt || '请选择要分析的选项：';
    contentDiv.appendChild(title);
    
    // 选项列表
    const optionsList = document.createElement('div');
    optionsList.className = 'selection-options';
    
    data.options.forEach((option, index) => {
        const optionDiv = document.createElement('div');
        optionDiv.className = 'selection-option';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.id = `option-${index}`;
        checkbox.value = index;
        
        // 如果是主要功能且设置了默认选中，则默认选中
        if (data.selection_type === 'functions' && option.is_primary && data.default_selected && data.default_selected.includes(index)) {
            checkbox.checked = true;
        }
        
        const label = document.createElement('label');
        label.htmlFor = `option-${index}`;
        label.style.cursor = 'pointer';
        label.style.display = 'flex';
        label.style.alignItems = 'flex-start';
        label.style.gap = '10px';
        label.style.padding = '10px';
        label.style.border = '1px solid #e9ecef';
        label.style.borderRadius = '8px';
        label.style.marginBottom = '8px';
        label.style.transition = 'all 0.2s';
        
        // 如果是主要功能，突出显示
        if (data.selection_type === 'functions' && option.is_primary) {
            label.style.border = '2px solid #4caf50';
            label.style.background = '#f1f8f4';
        }
        
        // 如果默认选中，应用选中样式
        if (checkbox.checked) {
            label.style.background = '#e3f2fd';
            label.style.borderColor = '#667eea';
        }
        
        label.addEventListener('mouseenter', () => {
            if (!checkbox.checked) {
                label.style.background = '#f8f9fa';
            }
        });
        label.addEventListener('mouseleave', () => {
            if (!checkbox.checked) {
                label.style.background = 'transparent';
            }
        });
        
        checkbox.addEventListener('change', () => {
            if (checkbox.checked) {
                label.style.background = '#e3f2fd';
                label.style.borderColor = '#667eea';
            } else {
                label.style.background = 'transparent';
                label.style.borderColor = '#e9ecef';
            }
        });
        
        const optionText = document.createElement('div');
        optionText.style.flex = '1';
        
        if (data.selection_type === 'contradictions') {
            const improveName = option.improve_param_name || `参数${option.improve_param}`;
            const worsenName = option.worsen_param_name || `参数${option.worsen_param}`;
            optionText.innerHTML = `<strong>改善参数</strong>: ${improveName}<br><strong>恶化参数</strong>: ${worsenName}`;
            if (option.description) {
                optionText.innerHTML += `<br><span style="color: #666; font-size: 12px;">${option.description}</span>`;
            }
        } else if (data.selection_type === 'functions') {
            let primaryBadge = '';
            if (option.is_primary) {
                primaryBadge = '<span style="background: #4caf50; color: white; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-left: 8px;">主要功能</span>';
            }
            optionText.innerHTML = `<strong>功能名称</strong>: ${option.function_name}${primaryBadge}<br><strong>类别</strong>: ${option.category}`;
            if (option.description) {
                optionText.innerHTML += `<br><span style="color: #666; font-size: 12px;">${option.description}</span>`;
            }
        }
        
        label.appendChild(checkbox);
        label.appendChild(optionText);
        optionDiv.appendChild(label);
        optionsList.appendChild(optionDiv);
    });
    
    contentDiv.appendChild(optionsList);
    
    // 按钮
    const buttonDiv = document.createElement('div');
    buttonDiv.style.display = 'flex';
    buttonDiv.style.gap = '10px';
    buttonDiv.style.marginTop = '15px';
    
    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = '确认分析';
    confirmBtn.className = 'selection-btn confirm-btn';
    confirmBtn.onclick = () => {
        const selected = Array.from(optionsList.querySelectorAll('input[type="checkbox"]:checked'))
            .map(cb => parseInt(cb.value));
        
        if (selected.length === 0) {
            showError('请至少选择一个选项');
            return;
        }
        
        processSelection(data, selected);
    };
    
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = '取消';
    cancelBtn.className = 'selection-btn cancel-btn';
    cancelBtn.onclick = () => {
        selectionDiv.remove();
        isLoading = false;
        sendBtn.disabled = false;
    };
    
    buttonDiv.appendChild(confirmBtn);
    buttonDiv.appendChild(cancelBtn);
    contentDiv.appendChild(buttonDiv);
    
    selectionDiv.appendChild(contentDiv);
    chatMessages.appendChild(selectionDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 处理用户选择
async function processSelection(selectionData, selectedIndices) {
    const selectionMsg = document.getElementById('selection-message');
    if (!selectionMsg) {
        return;
    }
    
    // 更新选择对话框，显示已选择的状态
    updateSelectionDialog(selectionMsg, selectionData, selectedIndices);
    
    showLoading();
    isLoading = true;
    sendBtn.disabled = true;
    
    try {
        const response = await fetch(getApiUrl('PROCESS_SELECTION'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                selection_type: selectionData.selection_type,
                selected_indices: selectedIndices,
                options: selectionData.options,
                message: selectionData.message,
                model: currentModel,
                session_id: sessionId
            })
        });
        
        // 检查响应状态
        if (!response.ok) {
            let errorMsg = `请求失败 (${response.status})`;
            try {
                const errorData = await response.json();
                errorMsg = errorData.error || errorMsg;
            } catch (e) {
                errorMsg = `服务器错误 (${response.status} ${response.statusText})`;
            }
            throw new Error(errorMsg);
        }
        
        const data = await response.json();
        
        // 如果有进度信息，先显示进度
        if (data.progress && data.progress.length > 0) {
            showProgress(data.progress);
            await new Promise(resolve => setTimeout(resolve, 500));
        }
        
        hideLoading();
        
        // 更新选择对话框，显示分析完成
        updateSelectionDialogComplete(selectionMsg, selectedIndices.length);
        
        // 在选择对话框下方添加分析结果（优先使用models数组，如果没有则使用model）
        addMessage('assistant', data.response, data.models || (data.model ? [data.model] : null));
        
    } catch (error) {
        console.error('处理选择失败:', error);
        hideLoading();
        
        // 更详细的错误信息
        let errorMessage = '处理选择失败';
        if (error.message) {
            errorMessage += ': ' + error.message;
        } else if (error.name === 'TypeError' && error.message && error.message.includes('fetch')) {
            errorMessage = '无法连接到服务器，请检查后端服务是否正常运行';
        } else {
            errorMessage += ': ' + (error.toString() || '未知错误');
        }
        
        showError(errorMessage);
    } finally {
        isLoading = false;
        sendBtn.disabled = false;
    }
}

// 更新选择对话框，显示已选择的状态
function updateSelectionDialog(selectionMsg, selectionData, selectedIndices) {
    const contentDiv = selectionMsg.querySelector('.selection-content');
    if (!contentDiv) return;
    
    // 禁用所有复选框和按钮
    const checkboxes = contentDiv.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(cb => {
        cb.disabled = true;
        if (!selectedIndices.includes(parseInt(cb.value))) {
            // 未选中的选项变灰
            const label = contentDiv.querySelector(`label[for="${cb.id}"]`);
            if (label) {
                label.style.opacity = '0.5';
                label.style.cursor = 'not-allowed';
            }
        }
    });
    
    // 禁用按钮
    const buttons = contentDiv.querySelectorAll('.selection-btn');
    buttons.forEach(btn => {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.style.cursor = 'not-allowed';
    });
    
    // 添加已选择提示
    const selectedInfo = document.createElement('div');
    selectedInfo.style.marginTop = '15px';
    selectedInfo.style.padding = '10px';
    selectedInfo.style.background = '#e8f5e9';
    selectedInfo.style.border = '1px solid #4caf50';
    selectedInfo.style.borderRadius = '8px';
    selectedInfo.style.fontSize = '14px';
    selectedInfo.style.color = '#2e7d32';
    
    const selectedOptions = selectedIndices.map(idx => {
        const option = selectionData.options[idx];
        if (selectionData.selection_type === 'contradictions') {
            const improveName = option.improve_param_name || `参数${option.improve_param}`;
            const worsenName = option.worsen_param_name || `参数${option.worsen_param}`;
            return `• ${improveName} vs ${worsenName}`;
        } else if (selectionData.selection_type === 'functions') {
            return `• ${option.function_name} (${option.category})`;
        }
        return '';
    }).filter(s => s).join('<br>');
    
    selectedInfo.innerHTML = `<strong>✓ 已选择 ${selectedIndices.length} 个选项，正在分析...</strong><br>${selectedOptions}`;
    selectedInfo.id = 'selection-status';
    
    // 移除按钮区域，添加已选择提示
    const buttonDiv = contentDiv.querySelector('div[style*="display: flex"]');
    if (buttonDiv) {
        buttonDiv.replaceWith(selectedInfo);
    } else {
        contentDiv.appendChild(selectedInfo);
    }
}

// 更新选择对话框，显示分析完成
function updateSelectionDialogComplete(selectionMsg, selectedCount) {
    const statusDiv = selectionMsg.querySelector('#selection-status');
    if (statusDiv) {
        statusDiv.innerHTML = statusDiv.innerHTML.replace('正在分析...', '✓ 分析完成');
        statusDiv.style.background = '#e3f2fd';
        statusDiv.style.borderColor = '#2196f3';
        statusDiv.style.color = '#1565c0';
    }
}

// 显示错误消息
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = '❌ ' + message;
    chatMessages.appendChild(errorDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // 3秒后自动移除
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

// 清空对话
async function clearChat() {
    if (!confirm('确定要清空所有对话记录吗？')) {
        return;
    }
    
    try {
        await fetch(getApiUrl('CLEAR'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                session_id: sessionId
            })
        });
        
        // 清空界面
        chatMessages.innerHTML = `
            <div class="welcome-message">
                <p><img src="/static/triz.png" alt="TRIZ" style="width: 24px; height: 24px; vertical-align: middle; margin-right: 8px;"> 欢迎使用InventBot！</p>
                <p>对话已清空，可以开始新的对话了。</p>
                <div style="margin-top: 20px; padding: 15px; background: #f0f0f0; border-radius: 8px; text-align: left;">
                    <p style="font-weight: bold; margin-bottom: 10px;">💡 使用示例：</p>
                    <p style="margin: 8px 0;"><strong>矛盾问题示例：</strong>我想把手表全部包裹起来，以实现游泳时可以防水；但是我不能，因为这样会导致无法听到手表扬声器的声音</p>
                    <p style="margin: 8px 0;"><strong>科学效应问题示例：</strong>电热水壶的水温达到100摄氏度时切断电源</p>
                </div>
            </div>
        `;
        
        // 创建新会话
        sessionId = 'session_' + Date.now();
        
    } catch (error) {
        console.error('清空对话失败:', error);
        showError('清空对话失败');
    }
}
