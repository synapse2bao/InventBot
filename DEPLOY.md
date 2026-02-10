# 静态部署指南

本应用支持前后端分离部署，前端可以部署到任何静态托管服务。

## 部署架构

- **前端**：纯静态文件（HTML/CSS/JS），可部署到 GitHub Pages、Netlify、Vercel 等
- **后端**：Flask API 服务，需要部署到支持 Python 的服务器

## 前端静态部署

### 方法1：GitHub Pages

1. **准备静态文件**
   ```bash
   # 复制静态文件到部署目录
   mkdir deploy
   cp static/* deploy/
   ```

2. **修改 config.js**
   编辑 `deploy/config.js`，设置后端API地址：
   ```javascript
   const API_BASE_URL = 'https://your-backend-server.com';
   ```

3. **推送到 GitHub**
   ```bash
   cd deploy
   git init
   git add .
   git commit -m "Deploy frontend"
   git branch -M main
   git remote add origin https://github.com/yourusername/yourrepo.git
   git push -u origin main
   ```

4. **启用 GitHub Pages**
   - 进入仓库 Settings → Pages
   - 选择 main 分支和 / (root) 目录
   - 保存后访问 `https://yourusername.github.io/yourrepo/`

### 方法2：Netlify

1. **创建 `netlify.toml`**（已创建）
   ```toml
   [build]
     publish = "static"
   
   [[redirects]]
     from = "/*"
     to = "/index.html"
     status = 200
   ```

2. **部署**
   - 将 `static` 目录推送到 GitHub
   - 在 Netlify 中连接仓库
   - 设置构建目录为 `static`
   - 部署

3. **配置环境变量**（如果需要）
   - 在 Netlify 设置中添加环境变量
   - 或直接修改 `config.js` 文件

### 方法3：Vercel

1. **创建 `vercel.json`**（已创建）
   ```json
   {
     "rewrites": [
       { "source": "/(.*)", "destination": "/index.html" }
     ]
   }
   ```

2. **部署**
   ```bash
   npm i -g vercel
   cd static
   vercel
   ```

### 方法4：直接使用静态文件服务器

1. **使用 Python 简单服务器**
   ```bash
   cd static
   python -m http.server 8000
   ```

2. **使用 Nginx**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       root /path/to/static;
       index index.html;
       
       location / {
           try_files $uri $uri/ /index.html;
       }
   }
   ```

## 后端部署

### 方法1：Railway

1. **创建 `Procfile`**（已创建）
   ```
   web: python app.py
   ```

2. **部署**
   - 在 Railway 中创建新项目
   - 连接 GitHub 仓库
   - 设置环境变量（API密钥）
   - 自动部署

### 方法2：Render

1. **创建 `render.yaml`**（已创建）

2. **部署**
   - 在 Render 中创建 Web Service
   - 连接 GitHub 仓库
   - 设置环境变量
   - 部署

### 方法3：Heroku

1. **创建 `Procfile`**（已创建）

2. **部署**
   ```bash
   heroku create your-app-name
   heroku config:set DEEPSEEK_API_KEY=your_key
   git push heroku main
   ```

### 方法4：自建服务器

1. **使用 Gunicorn**
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

2. **使用 Nginx 反向代理**
   ```nginx
   server {
       listen 80;
       server_name api.your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

## 配置 CORS

如果前后端分离部署，需要配置 CORS。后端已启用 CORS，但可能需要调整：

编辑 `app.py`：
```python
CORS(app, resources={
    r"/api/*": {
        "origins": ["https://your-frontend-domain.com"],
        "methods": ["GET", "POST"],
        "allow_headers": ["Content-Type"]
    }
})
```

## 环境变量配置

### 前端（config.js）
```javascript
const API_BASE_URL = 'https://your-backend-api.com';
```

### 后端（.env）
```
DEEPSEEK_API_KEY=your_key
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
GOOGLE_API_KEY=your_key
```

## 完整部署示例

### 前端：Netlify
- 地址：`https://chatbot-frontend.netlify.app`
- 配置：`config.js` 中设置 `API_BASE_URL = 'https://chatbot-api.railway.app'`

### 后端：Railway
- 地址：`https://chatbot-api.railway.app`
- 环境变量：在 Railway 控制台设置 API 密钥

## 注意事项

1. **HTTPS**：确保前后端都使用 HTTPS
2. **CORS**：正确配置跨域请求
3. **API密钥**：不要在前端代码中暴露 API 密钥
4. **环境变量**：使用环境变量管理敏感信息
