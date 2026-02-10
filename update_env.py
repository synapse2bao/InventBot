#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
更新 .env 文件中的 DEEPSEEK_API_KEY
"""

import sys
import os
import re
from pathlib import Path

def update_env_file(api_key, env_path=None):
    """
    更新或添加 DEEPSEEK_API_KEY 到 .env 文件
    
    Args:
        api_key: DeepSeek API KEY
        env_path: .env 文件路径，如果为 None，则在 setup_deepseek_key.html 所在目录查找
    
    Returns:
        tuple: (success: bool, message: str)
    """
    # 去除首尾的引号和空白
    api_key = api_key.strip()
    if api_key.startswith("'") and api_key.endswith("'"):
        api_key = api_key[1:-1]
    elif api_key.startswith('"') and api_key.endswith('"'):
        api_key = api_key[1:-1]
    api_key = api_key.strip()
    
    if not api_key:
        return False, "API KEY 不能为空"
    
    # 确定 .env 文件路径
    if env_path is None:
        # 获取 setup_deepseek_key.html 所在目录
        # 先尝试在当前脚本所在目录查找
        script_dir = Path(__file__).parent.absolute()
        setup_html_path = script_dir / 'setup_deepseek_key.html'
        
        if setup_html_path.exists():
            # 如果找到 setup_deepseek_key.html，使用其所在目录
            env_path = script_dir / '.env'
        else:
            # 如果找不到，尝试在父目录查找
            parent_dir = script_dir.parent
            setup_html_path = parent_dir / 'setup_deepseek_key.html'
            if setup_html_path.exists():
                env_path = parent_dir / '.env'
            else:
                # 如果都找不到，使用脚本所在目录
                env_path = script_dir / '.env'
    else:
        env_path = Path(env_path)
    
    # 读取现有内容
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, f"读取文件失败: {str(e)}"
    else:
        content = ""
    
    # 更新或添加 DEEPSEEK_API_KEY
    api_key_line = f"DEEPSEEK_API_KEY={api_key}\n"
    
    # 检查是否已存在 DEEPSEEK_API_KEY
    pattern = r'^DEEPSEEK_API_KEY=.*$'
    if re.search(pattern, content, re.MULTILINE):
        # 替换现有的
        new_content = re.sub(pattern, f'DEEPSEEK_API_KEY={api_key}', content, flags=re.MULTILINE)
        # 确保行尾有换行
        if not new_content.endswith('\n'):
            new_content += '\n'
    else:
        # 添加新的
        if content and not content.endswith('\n'):
            content += '\n'
        new_content = content + api_key_line
    
    # 写回文件
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True, f".env 文件已成功更新: {env_path}"
    except Exception as e:
        return False, f"写入文件失败: {str(e)}"


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python update_env.py <API_KEY> [env_file_path]")
        print("示例: python update_env.py sk-xxxxx")
        print("示例: python update_env.py sk-xxxxx C:\\path\\to\\.env")
        sys.exit(1)
    
    api_key = sys.argv[1]
    env_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    success, message = update_env_file(api_key, env_path)
    
    if success:
        print(message)
        sys.exit(0)
    else:
        print(f"错误: {message}", file=sys.stderr)
        sys.exit(1)
