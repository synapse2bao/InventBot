#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试模型列表API
"""
import requests
import json

def test_models_api():
    """测试模型列表API"""
    try:
        response = requests.get('http://localhost:5000/api/models')
        data = response.json()
        
        print("=" * 50)
        print("模型列表API测试结果")
        print("=" * 50)
        print(f"状态码: {response.status_code}")
        print(f"返回数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
        print()
        
        if 'models' in data:
            print(f"模型数量: {len(data['models'])}")
            print("\n模型列表:")
            for i, model in enumerate(data['models'], 1):
                print(f"  {i}. ID: {model.get('id')}, 名称: {model.get('name')}, 可用: {model.get('available')}")
            
            # 检查DeepSeek模型
            deepseek_models = [m for m in data['models'] if 'deepseek' in m.get('id', '')]
            print(f"\nDeepSeek模型数量: {len(deepseek_models)}")
            if len(deepseek_models) == 2:
                print("✓ DeepSeek模型配置正确！")
            elif len(deepseek_models) == 1:
                print("⚠ 警告：只检测到一个DeepSeek模型，请重启后端服务")
            else:
                print("✗ 未检测到DeepSeek模型")
        else:
            print("✗ API返回格式错误")
            
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到后端服务，请确保后端正在运行")
        print("  运行命令: python app.py")
    except Exception as e:
        print(f"✗ 测试失败: {e}")

if __name__ == '__main__':
    test_models_api()
