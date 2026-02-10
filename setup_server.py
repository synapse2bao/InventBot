# 简单的配置服务器，用于接收和保存 DeepSeek API KEY

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import subprocess
import sys
import time
from dotenv import load_dotenv, set_key
import openai

app = Flask(__name__)
CORS(app)

load_dotenv()

def test_deepseek_api_key(api_key):
    """测试DeepSeek API KEY是否有效"""
    if not api_key or api_key.strip() == '':
        return False, "API KEY为空"
    
    try:
        test_client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        # 发送一个简单的测试请求
        response = test_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5,
            timeout=10.0
        )
        if response and response.choices:
            return True, "API KEY有效"
        else:
            return False, "API响应异常"
    except openai.AuthenticationError:
        return False, "API KEY无效或已过期"
    except openai.RateLimitError:
        return False, "API KEY有效，但已达到速率限制"
    except Exception as e:
        error_msg = str(e).lower()
        if 'unauthorized' in error_msg or 'invalid' in error_msg or '401' in error_msg:
            return False, "API KEY无效或已过期"
        elif 'timeout' in error_msg or 'timed out' in error_msg:
            return False, "连接超时，请检查网络"
        else:
            return False, f"验证失败：{str(e)[:50]}"

@app.route('/')
def index():
    """返回配置页面"""
    return send_from_directory('.', 'setup_deepseek_key.html')

@app.route('/api/check-key', methods=['GET'])
def check_key():
    """检查是否已配置API KEY"""
    api_key = os.getenv('DEEPSEEK_API_KEY')
    return jsonify({
        'has_key': bool(api_key and api_key.strip() != '')
    })

@app.route('/api/save-key', methods=['POST'])
def save_key():
    """保存并验证API KEY"""
    data = request.json
    api_key = data.get('api_key', '').strip()
    
    # 去除首尾的单引号和双引号
    if api_key.startswith("'") and api_key.endswith("'"):
        api_key = api_key[1:-1]
    elif api_key.startswith('"') and api_key.endswith('"'):
        api_key = api_key[1:-1]
    api_key = api_key.strip()
    
    if not api_key:
        return jsonify({'success': False, 'error': 'API KEY不能为空'}), 400
    
    # 验证API KEY
    is_valid, message = test_deepseek_api_key(api_key)
    
    if not is_valid:
        return jsonify({'success': False, 'error': message}), 400
    
    # 保存到.env文件
    try:
        env_path = '.env'
        if not os.path.exists(env_path):
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('')
        
        set_key(env_path, 'DEEPSEEK_API_KEY', api_key)
        return jsonify({'success': True, 'message': 'API KEY已保存'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'保存失败：{str(e)}'}), 500

@app.route('/api/start-backend', methods=['POST'])
def start_backend():
    """启动后端服务"""
    try:
        # 获取当前脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        app_py = os.path.join(script_dir, 'app.py')
        
        if not os.path.exists(app_py):
            return jsonify({'success': False, 'error': '找不到app.py文件'}), 404
        
        # 检查后端是否已经在运行
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 5000))
            sock.close()
            if result == 0:
                # 端口已被占用，说明后端已在运行
                return jsonify({'success': True, 'message': '后端服务已在运行'})
        except:
            pass
        
        # 在Windows上直接启动Python程序（不等待完成）
        if sys.platform == 'win32':
            # 使用CREATE_NEW_CONSOLE标志在新窗口中运行Python程序
            # 使用pythonw.exe可以避免显示控制台窗口（如果需要的话）
            # 这里使用python.exe以便看到输出
            subprocess.Popen(
                [sys.executable, app_py],
                cwd=script_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            # 非Windows系统，直接运行
            subprocess.Popen(
                [sys.executable, app_py],
                cwd=script_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        
        # 等待几秒让后端启动
        time.sleep(3)
        
        return jsonify({'success': True, 'message': '后端服务正在启动'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'启动失败：{str(e)}'}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("DeepSeek API KEY 配置服务器")
    print("=" * 60)
    print("服务器地址: http://localhost:5001")
    print("请在浏览器中打开配置页面")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5001, debug=False)
