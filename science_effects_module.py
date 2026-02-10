# TRIZ科学效应模块
# 用于处理科学效应数据库的查询和解析

import os
import re
from bs4 import BeautifulSoup

def get_function_list():
    """
    获取function目录下的所有功能列表
    :return: 功能列表（文件名去掉.html后缀）
    """
    function_dir = "scienceeffects/function"
    functions = []
    if os.path.exists(function_dir):
        for filename in os.listdir(function_dir):
            if filename.endswith('.html'):
                function_name = filename[:-5]  # 去掉.html后缀
                functions.append(function_name)
    return sorted(functions)

def get_parameter_list():
    """
    获取parameter目录下的所有功能列表
    :return: 功能列表（文件名去掉.html后缀）
    """
    parameter_dir = "scienceeffects/parameter"
    parameters = []
    if os.path.exists(parameter_dir):
        for filename in os.listdir(parameter_dir):
            if filename.endswith('.html'):
                parameter_name = filename[:-5]  # 去掉.html后缀
                parameters.append(parameter_name)
    return sorted(parameters)

def get_transform_list():
    """
    获取transform目录下的所有功能列表
    :return: 功能列表（文件名去掉.html后缀）
    """
    transform_dir = "scienceeffects/transform"
    transforms = []
    if os.path.exists(transform_dir):
        for filename in os.listdir(transform_dir):
            if filename.endswith('.html'):
                transform_name = filename[:-5]  # 去掉.html后缀
                transforms.append(transform_name)
    return sorted(transforms)

def get_effect_data_from_db(function_name, category):
    """
    从数据库获取科学效应数据
    :param function_name: 功能名称
    :param category: 类别
    :return: 包含科学效应列表和详细解释的字典，格式与parse_effect_html相同
    """
    try:
        from database import get_science_effects_by_function
        effects = get_science_effects_by_function(function_name, category)
        
        if not effects:
            return None
        
        effect_list = []
        effect_details = []
        
        for effect in effects:
            effect_list.append({
                'name': effect['name'],
                'id': effect.get('id', '')
            })
            
            effect_details.append({
                'name': effect['name'],
                'description': effect.get('description', ''),
                'example': effect.get('example', ''),
                'wikipedia_link': effect.get('wikipedia_link', '')
            })
        
        return {
            'effect_list': effect_list,
            'effect_details': effect_details
        }
    except ImportError:
        return None
    except Exception as e:
        print(f"从数据库读取科学效应失败: {e}")
        return None

def parse_effect_html(html_path=None, function_name=None, category=None):
    """
    解析科学效应HTML文件或从数据库读取，提取科学效应列表和详细解释
    优先从数据库读取，如果数据库中没有则从HTML文件读取
    :param html_path: HTML文件路径（可选）
    :param function_name: 功能名称（可选，用于从数据库查询）
    :param category: 类别（可选，用于从数据库查询）
    :return: 包含科学效应列表和详细解释的字典
    """
    # 优先从数据库读取
    if function_name and category:
        db_data = get_effect_data_from_db(function_name, category)
        if db_data:
            return db_data
    
    # 如果数据库中没有或数据库不可用，从HTML文件读取
    if not html_path or not os.path.exists(html_path):
        return None
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"读取HTML文件失败: {e}")
        return None
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 提取科学效应列表（在<ul>标签中，查找所有包含result_effect的链接）
        effect_list = []
        # 查找所有包含result_effect类的链接
        effect_links = soup.find_all('a', class_='result_effect')
        for a_tag in effect_links:
            effect_name = a_tag.get_text(strip=True)
            effect_id = a_tag.get('href', '').replace('#', '')
            if effect_name:  # 确保名称不为空
                effect_list.append({
                    'name': effect_name,
                    'id': effect_id
                })
        
        # 如果没有找到，尝试从ul标签中查找
        if not effect_list:
            ul_tag = soup.find('ul')
            if ul_tag:
                for li in ul_tag.find_all('li'):
                    a_tag = li.find('a', class_='result_effect')
                    if a_tag:
                        effect_name = a_tag.get_text(strip=True)
                        effect_id = a_tag.get('href', '').replace('#', '')
                        if effect_name:
                            effect_list.append({
                                'name': effect_name,
                                'id': effect_id
                            })
        
        # 提取每个科学效应的详细解释（遍历所有results-row）
        effect_details = []
        results_rows = soup.find_all('div', class_='results-row')
        
        for row in results_rows:
            # 提取标题和链接
            title_tag = row.find('div', class_='results-title')
            if title_tag:
                a_tag = title_tag.find('a')
                if a_tag:
                    effect_name = a_tag.get_text(strip=True)
                    wiki_link = a_tag.get('href', '')
                else:
                    # 有些没有链接，尝试从id属性获取
                    effect_name = title_tag.get_text(strip=True)
                    # 尝试从id属性获取名称
                    effect_id = title_tag.get('id', '')
                    if not effect_name and effect_id:
                        # 如果标题为空，尝试从id查找对应的链接
                        id_link = soup.find('a', href=f"#{effect_id}")
                        if id_link:
                            effect_name = id_link.get_text(strip=True)
                    wiki_link = ''
                
                if effect_name:  # 只添加有名称的效应
                    # 提取描述
                    desc_tag = row.find('div', class_='results-desc')
                    description = desc_tag.get_text(strip=True) if desc_tag else ''
                    
                    # 提取示例
                    note_tag = row.find('div', class_='results-note')
                    example = note_tag.get_text(strip=True) if note_tag else ''
                    
                    effect_details.append({
                        'name': effect_name,
                        'description': description,
                        'example': example,
                        'wikipedia_link': wiki_link
                    })
        
        return {
            'effect_list': effect_list,
            'effect_details': effect_details
        }
    except Exception as e:
        print(f"解析HTML文件失败: {e}")
        return None

def find_effect_file(function_name, category='function'):
    """
    根据功能名称查找对应的HTML文件
    :param function_name: 功能名称
    :param category: 类别 ('function', 'parameter', 'transform')
    :return: HTML文件路径，如果不存在返回None
    """
    if category not in ['function', 'parameter', 'transform']:
        return None
    
    file_path = os.path.join('scienceeffects', category, f"{function_name}.html")
    
    if os.path.exists(file_path):
        return file_path
    
    return None

def get_effect_summary(html_path=None, function_name=None, category=None):
    """
    获取科学效应的摘要文本，用于输入给reasoner模型
    优先从数据库读取，如果数据库中没有则从HTML文件读取
    :param html_path: HTML文件路径（可选，用于回退）
    :param function_name: 功能名称（可选，用于从数据库查询）
    :param category: 类别（可选，用于从数据库查询）
    :return: 格式化的科学效应摘要文本
    """
    # 优先从数据库读取
    if function_name and category:
        try:
            from database import get_science_effect_summary
            summary = get_science_effect_summary(function_name, category)
            if summary:
                return summary
        except ImportError:
            pass
        except Exception as e:
            print(f"从数据库读取科学效应失败: {e}，回退到文件读取")
    
    # 如果数据库中没有或数据库不可用，从HTML文件读取
    if html_path and os.path.exists(html_path):
        parsed_data = parse_effect_html(html_path)
        if not parsed_data:
            return None
        
        summary = f"科学效应列表（共{len(parsed_data['effect_list'])}个）：\n"
        for i, effect in enumerate(parsed_data['effect_list'], 1):
            summary += f"{i}. {effect['name']}\n"
        
        summary += f"\n详细解释（共{len(parsed_data['effect_details'])}个）：\n"
        for i, effect in enumerate(parsed_data['effect_details'], 1):
            summary += f"\n【{i}. {effect['name']}】\n"
            if effect['description']:
                summary += f"描述：{effect['description']}\n"
            if effect['example']:
                summary += f"示例：{effect['example']}\n"
            if effect['wikipedia_link']:
                summary += f"维基百科链接：{effect['wikipedia_link']}\n"
        
        return summary
    
    return None
