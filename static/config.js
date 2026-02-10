// API配置 - 前后端已合并，使用当前域名
// 前后端运行在同一服务器上，直接使用当前页面的域名

const API_BASE_URL = window.location.origin;

// 导出配置
window.API_CONFIG = {
    BASE_URL: API_BASE_URL,
    ENDPOINTS: {
        MODELS: '/api/models',
        CHAT: '/api/chat',
        CLEAR: '/api/clear',
        PROCESS_SELECTION: '/api/process-selection'
    }
};
