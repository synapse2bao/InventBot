#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地服务器，用于接收 API KEY 并更新 .env 文件
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
from update_env import update_env_file

app = Flask(__name__)
CORS(app)

@app.route('/api/update-env', methods=['POST'])
def update_env():
    """更新 .env 文件中的 DEEPSEEK_API_KEY"""
    try:
        data = request.json
        api_key = data.get('api_key', '').strip()
        
        if not api_key:
            return jsonify({'success': False, 'error': 'API KEY 不能为空'}), 400
        
        # 获取项目根目录（脚本所在目录）
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(script_dir, '.env')
        
        # 更新 .env 文件
        success, message = update_env_file(api_key, env_path)
        
        if success:
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    print("=" * 60)
    print("DeepSeek API KEY 更新服务器")
    print("=" * 60)
    print("服务器地址: http://localhost:5002")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5002, debug=False)
