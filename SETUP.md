# 安装和配置指南

## 快速安装

### 1. 克隆仓库

```bash
git clone https://github.com/yourusername/inventbot.git
cd inventbot
```

### 2. 安装Python依赖

```bash
pip install -r requirements.txt
```

### 3. 配置API密钥

#### 方法一：使用配置向导（推荐）

1. 运行 `启动后端.bat`（Windows）或 `python app.py`（其他系统）
2. 如果未配置API密钥，系统会自动打开配置页面
3. 输入您的 DeepSeek API KEY
4. 点击"更新 .env 文件"按钮

#### 方法二：手动配置

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
```

### 4. 启动服务

**Windows:**
```bash
启动后端.bat
```

**Linux/Mac:**
```bash
python app.py
```

### 5. 访问应用

打开浏览器访问：`http://127.0.0.1:5000`

## 详细配置

### 端口配置

默认端口为 5000。如需修改，编辑 `app.py`：

```python
app.run(host='127.0.0.1', port=5000)  # 修改端口号
```

### API密钥获取

#### DeepSeek API KEY

1. 访问 [DeepSeek Platform](https://platform.deepseek.com/)
2. 注册/登录账户
3. 进入 API 管理页面
4. 创建新的 API KEY
5. 复制并配置


## 验证安装

启动后，访问 `http://127.0.0.1:5000`，如果看到Web界面，说明安装成功。

## 故障排除

### Python版本问题

确保使用 Python 3.8 或更高版本：

```bash
python --version
```

### 依赖安装失败

尝试使用国内镜像：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 端口被占用

修改 `app.py` 中的端口号，或关闭占用5000端口的程序。

### 数据库错误

删除 `database.db` 文件，让系统重新创建。

## 下一步

安装完成后，请查看 [USAGE.md](USAGE.md) 了解如何使用系统。
