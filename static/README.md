# 静态文件部署说明

这个目录包含前端静态文件，可以部署到任何静态托管服务。

## 快速部署

### 1. 修改 API 配置

编辑 `config.js` 文件，设置后端 API 地址：

```javascript
// 开发环境（本地）
const API_BASE_URL = window.location.origin;

// 生产环境（修改为你的后端地址）
// const API_BASE_URL = 'https://your-backend-api.com';
```

### 2. 部署到静态托管

#### GitHub Pages
1. 将 `static` 目录内容推送到 GitHub
2. 在仓库设置中启用 GitHub Pages
3. 选择主分支和根目录

#### Netlify
1. 将 `static` 目录内容推送到 GitHub
2. 在 Netlify 中连接仓库
3. 设置发布目录为 `static`（或直接部署 static 目录内容）

#### Vercel
```bash
cd static
vercel
```

## 文件说明

- `index.html` - 主页面
- `style.css` - 样式文件
- `script.js` - JavaScript 逻辑
- `config.js` - API 配置文件（部署前需要修改）

## 注意事项

- 确保后端 API 已正确配置 CORS
- 前后端都需要使用 HTTPS（生产环境）
- 不要在前端代码中暴露 API 密钥
