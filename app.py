from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os
from dotenv import load_dotenv, set_key
import openai  # 仅用于DeepSeek（使用OpenAI兼容的API）
import re
import json
from datetime import datetime
import threading
from triz_module import (
    TRIZ_PARAMETERS, 
    SOFTWARE_PARAMETERS,
    get_contradiction_matrix, 
    get_principle_pdf_path, 
    read_pdf_content,
    get_principle_name
)
from science_effects_module import (
    get_function_list,
    get_parameter_list,
    get_transform_list,
    find_effect_file,
    get_effect_summary,
    parse_effect_html
)

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

# 检查DeepSeek API KEY（配置通过HTML页面完成，见setup_deepseek_key.html）
deepseek_key = os.getenv('DEEPSEEK_API_KEY')
if deepseek_key and deepseek_key.strip() != '':
    print("正在验证 DeepSeek API KEY...")
    is_valid, message = test_deepseek_api_key(deepseek_key)
    if is_valid:
        print(f"✓ DeepSeek API KEY 验证成功")
    else:
        print(f"✗ DeepSeek API KEY 验证失败：{message}")
        print("提示：请运行 启动后端.bat 重新配置 API KEY")
else:
    print("⚠ DeepSeek API KEY 未配置")
    print("提示：请运行 启动后端.bat 配置 API KEY")

app = Flask(__name__, static_folder='static', static_url_path='/static')
# 配置CORS（前后端已合并，但保留CORS以支持可能的跨域需求）
CORS(app, resources={
    r"/api/*": {
        "origins": "*",  # 生产环境建议设置为具体的前端域名
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# 初始化各模型客户端
deepseek_client = None

# 初始化DeepSeek (使用OpenAI兼容的API)
if os.getenv('DEEPSEEK_API_KEY'):
    try:
        deepseek_client = openai.OpenAI(
            api_key=os.getenv('DEEPSEEK_API_KEY'),
            base_url="https://api.deepseek.com"
        )
    except Exception as e:
        print(f"警告: DeepSeek 客户端初始化失败 ({e})，DeepSeek 模型将不可用")
        deepseek_client = None


# 存储对话历史
conversations = {}

# 日志文件锁，确保线程安全
log_lock = threading.Lock()

def log_ai_call(model_name, status, error=None, additional_info=None, exception=None):
    """
    记录AI模型调用日志
    :param model_name: 模型名称
    :param status: 状态 ('calling', 'success', 'error', 'timeout')
    :param error: 错误信息（如果有）
    :param additional_info: 额外信息（字典格式）
    :param exception: 异常对象（如果有，用于记录堆栈跟踪）
    """
    try:
        # 创建logs目录（如果不存在）
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 使用日期作为日志文件名
        log_filename = os.path.join(log_dir, f'ai_calls_{datetime.now().strftime("%Y%m%d")}.log')
        
        # 构建日志条目
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            'timestamp': timestamp,
            'model': model_name,
            'status': status,
        }
        
        if error:
            log_entry['error'] = str(error)
        
        # 如果有异常对象，记录详细的错误信息
        if exception:
            import traceback
            log_entry['error_type'] = type(exception).__name__
            log_entry['error_message'] = str(exception)
            log_entry['traceback'] = traceback.format_exc()
        
        if additional_info:
            log_entry.update(additional_info)
        
        # 线程安全地写入日志
        with log_lock:
            with open(log_filename, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                f.flush()  # 立即刷新到磁盘
    except Exception as e:
        # 日志记录失败不应该影响主程序
        print(f"日志记录失败: {e}")

def log_error(error_message, exception=None, context=None):
    """
    记录通用错误日志
    :param error_message: 错误消息
    :param exception: 异常对象（可选）
    :param context: 上下文信息（字典格式，可选）
    """
    try:
        # 创建logs目录（如果不存在）
        log_dir = 'logs'
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 使用日期作为日志文件名
        log_filename = os.path.join(log_dir, f'errors_{datetime.now().strftime("%Y%m%d")}.log')
        
        # 构建日志条目
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = {
            'timestamp': timestamp,
            'error_message': error_message,
        }
        
        # 如果有异常对象，记录详细的错误信息
        if exception:
            import traceback
            log_entry['error_type'] = type(exception).__name__
            log_entry['error_message'] = str(exception)
            log_entry['traceback'] = traceback.format_exc()
        
        if context:
            log_entry['context'] = context
        
        # 线程安全地写入日志
        with log_lock:
            with open(log_filename, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                f.flush()  # 立即刷新到磁盘
    except Exception as e:
        # 日志记录失败不应该影响主程序
        print(f"错误日志记录失败: {e}")

def get_conversation_history(session_id):
    """获取会话历史"""
    if session_id not in conversations:
        conversations[session_id] = []
    return conversations[session_id]

def add_to_history(session_id, role, content):
    """添加到会话历史"""
    history = get_conversation_history(session_id)
    history.append({"role": role, "content": content})
    # 限制历史长度，保留最近20轮对话
    if len(history) > 40:
        conversations[session_id] = history[-40:]

def retry_with_split_messages(messages, api_type, model, api_func, max_splits=3, retry_count=0, max_retries=3):
    """
    当遇到超时错误时，切分输入内容并重试
    :param messages: 原始消息列表
    :param api_type: API类型 ('deepseek')
    :param model: 模型名称
    :param api_func: API调用函数
    :param max_splits: 最大切分次数
    :param retry_count: 当前重试次数
    :param max_retries: 最大重试次数（默认3次）
    :return: (响应文本, 错误信息)
    """
    # 检查重试次数是否超过限制
    if retry_count >= max_retries:
        return None, f"重试次数已达上限（{max_retries}次），无法继续处理"
    # 找到最后一条用户消息（通常是需要处理的长内容）
    last_user_message = None
    last_user_index = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i]["role"] == "user":
            last_user_message = messages[i]["content"]
            last_user_index = i
            break
    
    if not last_user_message or len(last_user_message) < 500:
        # 如果消息太短，无法切分，直接返回错误
        return None, "输入内容过短，无法切分"
    
    # 计算切分大小（每次切分为原来的1/2）
    split_size = len(last_user_message) // 2
    if split_size < 200:
        # 如果切分后太小，不再切分
        return None, "内容已切分至最小，仍超时"
    
    print(f"检测到超时错误，尝试切分输入内容（当前长度: {len(last_user_message)}, 切分大小: {split_size}）")
    
    # 按段落或句子切分（优先按段落）
    chunks = []
    if '\n\n' in last_user_message:
        # 按段落切分
        paragraphs = last_user_message.split('\n\n')
        current_chunk = ""
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= split_size:
                current_chunk += (para + '\n\n' if current_chunk else para)
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
        if current_chunk:
            chunks.append(current_chunk.strip())
    elif '\n' in last_user_message:
        # 按行切分
        lines = last_user_message.split('\n')
        current_chunk = ""
        for line in lines:
            if len(current_chunk) + len(line) + 1 <= split_size:
                current_chunk += (line + '\n' if current_chunk else line)
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line
        if current_chunk:
            chunks.append(current_chunk.strip())
    else:
        # 按字符切分
        for i in range(0, len(last_user_message), split_size):
            chunks.append(last_user_message[i:i+split_size])
    
    if len(chunks) <= 1:
        # 无法切分，返回错误
        return None, "无法切分输入内容"
    
    print(f"已切分为 {len(chunks)} 个部分，逐个处理...")
    
    # 逐个处理切分后的内容
    all_responses = []
    base_messages = messages[:last_user_index]  # 保留前面的消息作为上下文
    
    for i, chunk in enumerate(chunks):
        print(f"处理第 {i+1}/{len(chunks)} 部分（长度: {len(chunk)}）...")
        
        # 构建新的消息列表
        chunk_messages = base_messages.copy()
        chunk_messages.append({
            "role": "user",
            "content": f"这是第{i+1}部分，共{len(chunks)}部分：\n\n{chunk}"
        })
        
        # 调用API（禁用进一步切分，避免无限递归）
        if api_type == 'deepseek':
            response_text, error = api_func(chunk_messages, model, retry_with_split=False)
        else:
            response_text, error = api_func(chunk_messages, model, retry_with_split=False)
        
        if error:
            # 如果某个部分仍然失败，检查是否为超时错误且未超过重试次数
            is_timeout = 'timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()
            if is_timeout and retry_count < max_retries and max_splits > 0:
                print(f"第 {i+1} 部分仍然超时（重试次数: {retry_count + 1}/{max_retries}），尝试进一步切分...")
                sub_response, sub_error = retry_with_split_messages(
                    chunk_messages, api_type, model, api_func, max_splits - 1, retry_count + 1, max_retries
                )
                if sub_response:
                    all_responses.append(sub_response)
                else:
                    all_responses.append(f"[第{i+1}部分处理失败: {sub_error}]")
            else:
                all_responses.append(f"[第{i+1}部分处理失败: {error}]")
        else:
            all_responses.append(response_text)
    
    # 拼接所有响应
    if all_responses:
        combined_response = "\n\n".join(all_responses)
        print(f"成功处理所有部分，总长度: {len(combined_response)}")
        return combined_response, None
    else:
        return None, "所有部分处理都失败"

def call_deepseek(messages, model="deepseek-chat", retry_with_split=True, retry_with_chat=False):
    """调用DeepSeek API，支持超时自动切分重试，reasoner模型超时改用chat模型重试"""
    if not deepseek_client:
        error_msg = "DeepSeek API密钥未配置"
        log_ai_call(model, 'error', error=error_msg)
        return None, error_msg
    
    try:
        # 记录调用开始
        log_ai_call(model, 'calling')
        
        response = deepseek_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            timeout=300.0  # 300秒超时
        )
        result = response.choices[0].message.content
        
        # 记录成功
        log_ai_call(model, 'success', additional_info={'response_length': len(result)})
        
        return result, None
    except Exception as e:
        error_str = str(e).lower()
        # 检测超时错误
        if retry_with_split and ('timeout' in error_str or 'timed out' in error_str or 'request timed out' in error_str):
            # 记录超时（包含异常对象）
            log_ai_call(model, 'timeout', error=str(e), exception=e)
            # 如果使用的是reasoner模型且未使用chat模型重试过，改用chat模型重试一次
            if model == 'deepseek-reasoner' and not retry_with_chat:
                print(f"Reasoner模型超时，改用chat模型重试...")
                return call_deepseek(messages, model="deepseek-chat", retry_with_split=False, retry_with_chat=True)
            # 否则尝试切分输入并重试（从第1次重试开始）
            return retry_with_split_messages(messages, 'deepseek', model, call_deepseek, max_splits=3, retry_count=1, max_retries=3)
        
        # 记录错误（包含异常对象）
        log_ai_call(model, 'error', error=str(e), exception=e)
        
        return None, str(e)

def check_contradiction(user_input, model="deepseek-chat", progress_steps=None):
    """
    使用chat模型判断用户输入是否存在矛盾，并识别是硬件矛盾还是软件矛盾
    :param user_input: 用户输入
    :param model: 使用的模型
    :param progress_steps: 进度步骤列表（可选）
    :return: (是否存在矛盾, 判断结果文本, 矛盾类型) 矛盾类型为'hardware'或'software'或None
    """
    prompt = f"""请严格按照以下文字描述本身来判断是否存在技术矛盾（即改善一个参数会导致另一个参数恶化的情况），并判断是硬件矛盾还是软件矛盾。

**重要要求**：
1. 只基于用户提供的文字描述本身进行判断，不要进行任何扩展、推理或假设
2. 如果文字描述中明确提到了"但是"、"然而"、"却"、"无法"、"不能"等表示矛盾的词语，且同时提到了改善和恶化的情况，则判断为存在矛盾
3. 如果文字描述中没有明确提到矛盾关系，即使可以推理出矛盾，也应判断为不存在矛盾
4. 不要添加任何文字描述中没有的信息
5. 判断矛盾类型：
   - 硬件矛盾：涉及物理实体、机械结构、材料属性等（如重量、体积、强度、温度等）
   - 软件矛盾：涉及软件系统、数据处理、信息处理等（如性能、数据量、处理速度、存储空间、易用性、可靠性等）

问题描述：{user_input}

请以JSON格式回答：
{{
    "has_contradiction": true/false,
    "contradiction_type": "hardware"/"software"/null,
    "explanation": "简要说明矛盾点（必须基于文字描述本身）"
}}"""
    
    messages = [{"role": "user", "content": prompt}]
    
    response_text, error = call_deepseek(messages, model="deepseek-chat")
    
    if error:
        return False, None, None
    
    # 尝试解析JSON
    contradiction_type = None
    try:
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            has_contradiction = result.get('has_contradiction', False)
            contradiction_type = result.get('contradiction_type')
            if contradiction_type not in ['hardware', 'software']:
                contradiction_type = None
            return has_contradiction, response_text, contradiction_type
    except:
        pass
    
    # 如果JSON解析失败，使用旧的方式判断
    has_contradiction = "是" in response_text or "存在" in response_text or "有" in response_text
    
    # 尝试从文本中推断矛盾类型
    if has_contradiction:
        software_keywords = ['软件', '数据', '处理', '存储', '性能', '速度', '吞吐量', '用户', '系统', '信息', '算法', '代码', '程序']
        hardware_keywords = ['重量', '体积', '长度', '面积', '强度', '温度', '材料', '机械', '物理', '结构']
        
        user_input_lower = user_input.lower()
        software_count = sum(1 for kw in software_keywords if kw in user_input_lower)
        hardware_count = sum(1 for kw in hardware_keywords if kw in user_input_lower)
        
        if software_count > hardware_count:
            contradiction_type = 'software'
        elif hardware_count > software_count:
            contradiction_type = 'hardware'
    
    return has_contradiction, response_text, contradiction_type

def extract_parameters(user_input, model="deepseek-chat", extract_multiple=False, progress_steps=None, contradiction_type='hardware'):
    """
    使用chat模型提炼改善的参数和恶化的参数
    :param user_input: 用户输入
    :param model: 使用的模型
    :param extract_multiple: 是否提取多个矛盾组合
    :param progress_steps: 进度步骤列表（可选）
    :param contradiction_type: 矛盾类型，'hardware'表示硬件矛盾（使用39参数），'software'表示软件矛盾（使用24参数）
    :return: 如果extract_multiple=False，返回(改善参数编号, 恶化参数编号)或(None, None)
             如果extract_multiple=True，返回矛盾组合列表，格式为[{"improve_param": 1, "worsen_param": 2, ...}, ...]
    """
    
    # 根据矛盾类型选择参数列表
    if contradiction_type == 'software':
        param_list = "\n".join([f"{i+1}. {param}" for i, param in enumerate(SOFTWARE_PARAMETERS)])
        max_param = 24
        param_type_name = "软件"
    else:
        param_list = "\n".join([f"{i+1}. {param}" for i, param in enumerate(TRIZ_PARAMETERS)])
        max_param = 39
        param_type_name = "硬件"
    
    if extract_multiple:
        prompt = f"""请分析以下问题描述，识别出所有可能的改善参数和恶化参数的组合。

**重要要求**：
1. 改善参数和恶化参数必须从以下参数列表中选择，不能新增或自定义参数
2. 只能选择参数编号在1-{max_param}范围内的参数
3. 参数名称必须与列表中的参数名称完全匹配或高度相似

问题描述：{user_input}

可选{param_type_name}参数列表：
{param_list}

请以JSON格式回答，格式如下（如果有多个矛盾，请列出所有）：
{{
    "contradictions": [
        {{
            "improve_param": 参数编号（1-{max_param}，必须从列表中选择）,
            "worsen_param": 参数编号（1-{max_param}，必须从列表中选择）,
            "improve_param_name": "参数名称（必须与列表中的名称匹配）",
            "worsen_param_name": "参数名称（必须与列表中的名称匹配）",
            "description": "矛盾描述"
        }},
        ...
    ]
}}

只返回JSON，不要其他文字。如果只有一个矛盾，也要放在数组中。"""
    else:
        prompt = f"""请分析以下问题描述，识别出改善的参数和恶化的参数。

**重要要求**：
1. 改善参数和恶化参数必须从以下参数列表中选择，不能新增或自定义参数
2. 只能选择参数编号在1-{max_param}范围内的参数
3. 参数名称必须与列表中的参数名称完全匹配或高度相似

问题描述：{user_input}

可选{param_type_name}参数列表：
{param_list}

请以JSON格式回答，格式如下：
{{
    "improve_param": 参数编号（1-{max_param}，必须从列表中选择）,
    "worsen_param": 参数编号（1-{max_param}，必须从列表中选择）,
    "improve_param_name": "参数名称（必须与列表中的名称匹配）",
    "worsen_param_name": "参数名称（必须与列表中的名称匹配）"
}}

只返回JSON，不要其他文字。"""
    
    messages = [{"role": "user", "content": prompt}]
    
    if model == 'deepseek-chat':
        response_text, error = call_deepseek(messages, model="deepseek-chat")
    else:
        response_text, error = call_deepseek(messages, model="deepseek-chat")
    
    if error:
        return [] if extract_multiple else (None, None)
    
    # 尝试从响应中提取JSON
    try:
        # 查找JSON部分（支持多行JSON）
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            
            if extract_multiple:
                # 返回多个矛盾组合
                contradictions = result.get('contradictions', [])
                if isinstance(contradictions, list) and len(contradictions) > 0:
                    return contradictions
                # 如果只有一个矛盾但格式不对，尝试转换
                if result.get('improve_param') and result.get('worsen_param'):
                    return [result]
            else:
                # 返回单个矛盾
                improve_param = result.get('improve_param')
                worsen_param = result.get('worsen_param')
                if improve_param and worsen_param:
                    return int(improve_param), int(worsen_param)
    except Exception as e:
        error_msg = f"JSON解析错误: {e}"
        log_error(error_msg, exception=e, context={'function': 'extract_parameters', 'user_input': user_input[:100] if user_input else None})
        print(error_msg)
        pass
    
    # 如果JSON解析失败，尝试从文本中提取数字
    if not extract_multiple:
        numbers = re.findall(r'\d+', response_text)
        if len(numbers) >= 2:
            try:
                improve_param = int(numbers[0])
                worsen_param = int(numbers[1])
                if 1 <= improve_param <= 39 and 1 <= worsen_param <= 39:
                    return improve_param, worsen_param
            except:
                pass
    
    return [] if extract_multiple else (None, None)

def get_principle_descriptions(principle_nums):
    """
    根据发明原则编号获取原则描述（优先从数据库读取）
    :param principle_nums: 发明原则编号列表
    :return: 原则描述字典列表
    """
    try:
        # 优先从数据库读取
        from database import get_principles_by_numbers
        db_principles = get_principles_by_numbers([n for n in principle_nums if n != 0])
        
        # 创建编号到原则的映射
        principle_map = {p['number']: p for p in db_principles}
        
        principles = []
        for num in principle_nums:
            if num == 0:
                continue
            
            if num in principle_map:
                # 从数据库获取
                principle = principle_map[num]
                principles.append({
                    "number": principle['number'],
                    "name": principle['name'],
                    "description": principle['content']
                })
            else:
                # 数据库中没有，回退到文件读取
                principle_name = get_principle_name(num)
                pdf_path = get_principle_pdf_path(num)
                
                description = ""
                if pdf_path and os.path.exists(pdf_path):
                    description = read_pdf_content(pdf_path)
                    if not description:
                        description = f"原则{num}: {principle_name}（PDF读取失败）"
                else:
                    description = f"原则{num}: {principle_name}（PDF文件不存在）"
                
                principles.append({
                    "number": num,
                    "name": principle_name,
                    "description": description
                })
        
        return principles
    except ImportError:
        # 如果数据库模块不可用，使用原来的文件读取方式
        principles = []
        for num in principle_nums:
            if num == 0:
                continue
            
            principle_name = get_principle_name(num)
            pdf_path = get_principle_pdf_path(num)
            
            description = ""
            if pdf_path and os.path.exists(pdf_path):
                description = read_pdf_content(pdf_path)
                if not description:
                    description = f"原则{num}: {principle_name}（PDF读取失败）"
            else:
                description = f"原则{num}: {principle_name}（PDF文件不存在）"
            
            principles.append({
                "number": num,
                "name": principle_name,
                "description": description
            })
        
        return principles

def solve_with_triz(user_input, principle_descriptions, model="deepseek-reasoner", progress_steps=None):
    """
    使用reasoner模型根据TRIZ原则解决问题
    :param user_input: 用户输入
    :param principle_descriptions: 发明原则描述列表
    :param model: 使用的模型
    :param progress_steps: 进度步骤列表（可选）
    :return: 解决方案文本
    """
    
    # 构建原则描述文本
    principle_text = ""
    for p in principle_descriptions:
        principle_text += f"\n原则{p['number']}: {p['name']}\n{p['description']}\n"
    
    prompt = f"""#role 你是一个TRIZ专家，用TRIZ发明原则解决问题

#问题描述：{user_input}

#发明原则：{principle_text}

请根据上述TRIZ发明原则，为问题提供解决方案。"""
    
    messages = [{"role": "user", "content": prompt}]
    
    if model == 'deepseek-reasoner':
        response_text, error = call_deepseek(messages, model="deepseek-reasoner")
        # 如果reasoner模型超时，改用chat模型重试一次
        if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
            print(f"Reasoner模型超时，改用chat模型重试...")
            response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
    else:
        response_text, error = call_deepseek(messages, model="deepseek-reasoner")
        # 如果reasoner模型超时，改用chat模型重试一次
        if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
            print(f"Reasoner模型超时，改用chat模型重试...")
            response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
    
    if error:
        return f"生成解决方案时出错: {error}"
    
    return response_text

def check_function_problem(user_input, model="deepseek-chat", progress_steps=None):
    """
    使用chat模型判断用户输入是否存在有问题的功能
    :param user_input: 用户输入
    :param model: 使用的模型
    :param progress_steps: 进度步骤列表（可选）
    :return: (是否存在问题功能, 判断结果文本)
    """
    
    prompt = f"""请严格按照以下文字描述本身来判断是否存在需要实现或改进的功能问题。

**重要要求**：
1. 只基于用户提供的文字描述本身进行判断，不要进行任何扩展、推理或假设
2. 如果文字描述中明确提到了需要实现的功能、需要改进的功能、或功能相关的问题，则判断为存在功能问题
3. 如果文字描述中没有明确提到功能问题，即使可以推理出功能需求，也应判断为不存在功能问题
4. 不要添加任何文字描述中没有的信息

问题描述：{user_input}

请只回答"是"或"否"，如果存在功能问题，请简要说明功能点（必须基于文字描述本身）。"""
    
    messages = [{"role": "user", "content": prompt}]
    
    response_text, error = call_deepseek(messages, model="deepseek-chat")
    
    if error:
        return False, None
    
    # 判断是否包含"是"或"存在"等肯定词
    has_problem = "是" in response_text or "存在" in response_text or "有" in response_text
    
    return has_problem, response_text

def extract_function(user_input, model="deepseek-chat", extract_multiple=False, progress_steps=None):
    """
    使用chat模型提炼存在问题的功能
    :param user_input: 用户输入
    :param model: 使用的模型
    :param extract_multiple: 是否提取多个功能问题
    :param progress_steps: 进度步骤列表（可选）
    :return: 如果extract_multiple=False，返回(功能名称, 类别)或(None, None)
             如果extract_multiple=True，返回功能问题列表，格式为[{"function_name": "...", "category": "...", ...}, ...]
    """
    
    # 获取所有功能列表
    function_list = get_function_list()
    parameter_list = get_parameter_list()
    transform_list = get_transform_list()
    
    # 构建功能列表字符串
    all_functions = []
    all_functions.append("function目录（动词+宾语格式）：")
    for func in function_list[:50]:  # 限制数量避免prompt过长
        all_functions.append(f"  - {func}")
    if len(function_list) > 50:
        all_functions.append(f"  ... 还有{len(function_list)-50}个功能")
    
    all_functions.append("\nparameter目录（动词+宾语格式）：")
    for param in parameter_list[:50]:
        all_functions.append(f"  - {param}")
    if len(parameter_list) > 50:
        all_functions.append(f"  ... 还有{len(parameter_list)-50}个功能")
    
    all_functions.append("\ntransform目录（场+场格式，表示从一个场转换成另一个场）：")
    for trans in transform_list[:50]:
        all_functions.append(f"  - {trans}")
    if len(transform_list) > 50:
        all_functions.append(f"  ... 还有{len(transform_list)-50}个功能")
    
    function_list_str = "\n".join(all_functions)
    
    if extract_multiple:
        prompt = f"""请分析以下问题描述，识别出所有存在问题的功能，并确定哪个是主要功能问题。

问题描述：{user_input}

可选功能列表：
{function_list_str}

**示例**：
用户输入：一个20g的物体在垂直管道里掉落，需要加快掉落速度并准确落入预设位置。
提取结果：
- 20g物体掉落，很可能是固体在运动，功能为移动固体，对应"Move Solid"
- 加快掉落速度的功能为增加速度，对应"Increase Speed"
- 准确落入预设位置的功能为定位固体，对应"Orient Solid"

请以JSON格式回答，格式如下（如果有多个功能问题，请列出所有，并按重要性排序，主要功能放在第一位）：
{{
    "functions": [
        {{
            "function_name": "功能名称（必须完全匹配列表中的某个功能）",
            "category": "function/parameter/transform",
            "description": "功能描述",
            "is_primary": true/false,
            "priority": 1
        }},
        ...
    ]
}}

**重要要求**：
1. 分析问题描述，确定哪个功能问题是用户最关心的核心问题（主要功能）
2. 将主要功能标记为 "is_primary": true，并设置 "priority": 1
3. 其他功能按重要性排序，主要功能必须放在数组的第一位
4. 如果只有一个功能，也要标记为主要功能

只返回JSON，不要其他文字。如果无法确定，请选择最接近的功能。"""
    else:
        prompt = f"""请分析以下问题描述，识别出存在问题的功能。

问题描述：{user_input}

可选功能列表：
{function_list_str}

**示例**：
用户输入：一个20g的物体在垂直管道里掉落，需要加快掉落速度并准确落入预设位置。
提取结果：
- 20g物体掉落，很可能是固体在运动，功能为移动固体，对应"Move Solid"
- 加快掉落速度的功能为增加速度，对应"Increase Speed"
- 准确落入预设位置的功能为定位固体，对应"Orient Solid"

请以JSON格式回答，格式如下：
{{
    "function_name": "功能名称（必须完全匹配列表中的某个功能）",
    "category": "function/parameter/transform",
    "description": "功能描述"
}}

只返回JSON，不要其他文字。如果无法确定，请选择最接近的功能。"""
    
    messages = [{"role": "user", "content": prompt}]
    
    if model == 'deepseek-chat':
        response_text, error = call_deepseek(messages, model="deepseek-chat")
    else:
        response_text, error = call_deepseek(messages, model="deepseek-chat")
    
    if error:
        return [] if extract_multiple else (None, None)
    
    # 尝试从响应中提取JSON
    try:
        # 查找JSON部分（支持多行JSON）
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            result = json.loads(json_str)
            
            if extract_multiple:
                # 返回多个功能问题
                functions = result.get('functions', [])
                if isinstance(functions, list) and len(functions) > 0:
                    # 验证所有功能是否都在数据库中
                    function_list = get_function_list()
                    parameter_list = get_parameter_list()
                    transform_list = get_transform_list()
                    
                    # 过滤掉不在数据库中的功能
                    valid_functions = []
                    for func in functions:
                        func_name = func.get('function_name')
                        func_category = func.get('category')
                        if func_category == 'function' and func_name in function_list:
                            valid_functions.append(func)
                        elif func_category == 'parameter' and func_name in parameter_list:
                            valid_functions.append(func)
                        elif func_category == 'transform' and func_name in transform_list:
                            valid_functions.append(func)
                    
                    if len(valid_functions) > 0:
                        # 确保至少有一个主要功能
                        has_primary = any(f.get('is_primary', False) for f in valid_functions)
                        if not has_primary:
                            # 如果没有标记主要功能，将第一个标记为主要功能
                            valid_functions[0]['is_primary'] = True
                            valid_functions[0]['priority'] = 1
                        return valid_functions
                # 如果只有一个功能但格式不对，尝试转换
                if result.get('function_name') and result.get('category'):
                    # 验证功能是否在数据库中
                    func_name = result.get('function_name')
                    func_category = result.get('category')
                    function_list = get_function_list()
                    parameter_list = get_parameter_list()
                    transform_list = get_transform_list()
                    
                    is_valid = False
                    if func_category == 'function' and func_name in function_list:
                        is_valid = True
                    elif func_category == 'parameter' and func_name in parameter_list:
                        is_valid = True
                    elif func_category == 'transform' and func_name in transform_list:
                        is_valid = True
                    
                    if is_valid:
                        result['is_primary'] = True
                        result['priority'] = 1
                        return [result]
            else:
                # 返回单个功能
                function_name = result.get('function_name')
                category = result.get('category')
                if function_name and category:
                    return function_name, category
    except Exception as e:
        error_msg = f"JSON解析错误: {e}"
        log_error(error_msg, exception=e, context={'function': 'extract_parameters', 'user_input': user_input[:100] if user_input else None})
        print(error_msg)
        pass
    
    # 如果JSON解析失败，尝试模糊匹配（仅单个模式）
    if not extract_multiple:
        keywords = user_input.lower().split()
        for func in function_list + parameter_list + transform_list:
            func_lower = func.lower()
            if any(keyword in func_lower for keyword in keywords if len(keyword) > 3):
                # 判断类别
                if func in function_list:
                    return func, 'function'
                elif func in parameter_list:
                    return func, 'parameter'
                elif func in transform_list:
                    return func, 'transform'
    
    return [] if extract_multiple else (None, None)

def filter_science_effects_with_chat(user_input, effect_names, chat_model="deepseek-chat", progress_steps=None):
    """
    使用chat模型筛选科学效应名称，选出有可能产生解决方案的科学效应
    :param user_input: 用户输入的问题描述
    :param effect_names: 科学效应名称列表
    :param chat_model: 使用的chat模型
    :param progress_steps: 进度步骤列表（可选）
    :return: 筛选后的科学效应名称列表
    """
    
    if not effect_names:
        return []
    
    # 构建效应名称列表文本
    effect_names_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(effect_names)])
    
    prompt = f"""#role 你是一个TRIZ专家，负责筛选可能相关的科学效应

#问题描述：{user_input}

#科学效应列表（共{len(effect_names)}个）：
{effect_names_text}

请根据问题描述，从上述科学效应列表中筛选出**有可能产生解决方案**的科学效应名称。
只返回筛选后的科学效应名称，每行一个，不要添加编号或其他说明文字。
如果某个科学效应的名称与问题相关，或者可能通过该效应解决问题，就将其包含在结果中。
请尽量筛选出所有可能相关的科学效应，不要过于严格。"""

    messages = [{"role": "user", "content": prompt}]
    
    # 使用chat模型进行筛选
    if chat_model == 'deepseek-chat' or chat_model == 'deepseek':
        response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
    else:
        # 默认使用deepseek-chat
        response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
    
    if error:
        print(f"筛选科学效应时出错: {error}，返回所有科学效应")
        return effect_names  # 如果筛选失败，返回所有效应
    
    # 解析返回的科学效应名称
    filtered_names = []
    lines = response_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 移除可能的编号（如 "1. " 或 "- "）
        line = re.sub(r'^[\d\-\.\s]+', '', line).strip()
        # 查找匹配的科学效应名称
        for effect_name in effect_names:
            if effect_name in line or line in effect_name:
                if effect_name not in filtered_names:
                    filtered_names.append(effect_name)
                break
    
    # 如果筛选结果为空，返回所有效应（避免丢失所有信息）
    if not filtered_names:
        print("筛选结果为空，返回所有科学效应")
        return effect_names
    
    print(f"筛选前: {len(effect_names)}个科学效应，筛选后: {len(filtered_names)}个科学效应")
    return filtered_names

def solve_with_science_effects(user_input, html_path=None, effect_summary=None, function_name=None, category=None, model="deepseek-reasoner", max_chars_per_batch=40000, progress_steps=None):
    """
    使用reasoner模型根据科学效应解决问题
    当数量<=30个时，使用完整的科学效应描述；当数量>30个时，只使用科学效应名称
    如果内容超长，会分批输入，然后本地组合输出结果
    :param user_input: 用户输入
    :param html_path: 科学效应HTML文件路径（可选，用于回退）
    :param effect_summary: 科学效应摘要文本（可选，如果其他方式都失败时使用）
    :param function_name: 功能名称（可选，用于从数据库查询）
    :param category: 类别（可选，用于从数据库查询）
    :param model: 使用的reasoner模型
    :param max_chars_per_batch: 每批最大字符数，默认40000
    :param progress_steps: 进度步骤列表（可选）
    :return: 解决方案文本
    """
    try:
        # 优先从数据库读取，如果没有则从HTML文件读取
        effect_count = 0
        effect_names_only = False
        parsed_data = None
        
        # 尝试从数据库或文件解析科学效应数据
        if function_name and category:
            parsed_data = parse_effect_html(html_path=html_path, function_name=function_name, category=category)
        elif html_path and os.path.exists(html_path):
            parsed_data = parse_effect_html(html_path=html_path)
        
        if parsed_data and parsed_data.get('effect_list'):
            effect_count = len(parsed_data['effect_list'])
            print(f"找到 {effect_count} 个科学效应")
            
            # 根据数量决定策略：<=30个使用完整描述，>30个只使用名称
            if effect_count <= 30:
                print(f"科学效应数量（{effect_count}个）<=30，使用完整描述")
                # 使用完整的科学效应描述
                effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
                effect_names_only = False
            else:
                print(f"科学效应数量（{effect_count}个）>30，只使用名称列表")
                # 只使用科学效应名称列表
                effect_names = [effect['name'] for effect in parsed_data['effect_list']]
                effect_summary = f"科学效应列表（共{len(effect_names)}个）：\n"
                for i, name in enumerate(effect_names, 1):
                    effect_summary += f"{i}. {name}\n"
                effect_names_only = True
        else:
            # 如果解析失败，尝试直接获取摘要
            if not effect_summary:
                effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
            if effect_summary:
                # 尝试从摘要中提取数量
                effect_count = len(effect_summary.split('【'))-1 if '【' in effect_summary else 0
        
        if not effect_summary:
            return "无法获取科学效应内容"
        
        # 根据是否只使用名称，构建不同的提示词模板
        if effect_names_only:
            # 只使用名称时的提示词模板
            base_prompt_template = """#role 你是一个TRIZ专家，用科学效应解决问题

#问题描述：{user_input}

#科学效应名称列表：{effect_summary}

**重要要求**：
1. 基于科学效应的名称，结合你的专业知识，推断每个科学效应的原理和应用方式
2. 必须遍历所有科学效应名称，分析每个科学效应如何应用于解决当前问题，为每个可能相关的科学效应提供具体的应用方案
3. 在单个科学效应方案的基础上，尝试组合多个科学效应，创造更好的综合解决方案，并说明各个科学效应如何协同工作


请根据上述科学效应名称，为问题提供推荐的解决方案。"""
        else:
            # 使用完整描述时的提示词模板
            base_prompt_template = """#role 你是一个TRIZ专家，用科学效应解决问题

#问题描述：{user_input}

#科学效应：{effect_summary}

**重要要求**：
1. 必须遍历所有科学效应，分析每个科学效应如何应用于解决当前问题
2. 为每个可能相关的科学效应提供具体的应用方案
3. 在单个科学效应方案的基础上，尝试组合多个科学效应，创造更好的综合解决方案
4. 优先考虑组合方案，因为组合多个科学效应往往能产生更创新、更有效的解决方案
5. 对于组合方案，要详细说明各个科学效应如何协同工作

请根据上述科学效应，为问题提供推荐的解决方案。"""
        
        # 构建完整提示词
        prompt = base_prompt_template.format(user_input=user_input, effect_summary=effect_summary)
        total_length = len(prompt)
        
        # 如果内容不超过限制，直接处理
        if total_length <= max_chars_per_batch:
            messages = [{"role": "user", "content": prompt}]
            
            
            if model == 'deepseek-reasoner':
                response_text, error = call_deepseek(messages, model="deepseek-reasoner")
            else:
                response_text, error = call_deepseek(messages, model="deepseek-reasoner")
            
            if error:
                return f"生成解决方案时出错: {error}"
            
            return response_text
        
        # 内容超长，需要分批处理
        # 计算基础提示词长度（不包含效应部分）
        base_prompt_without_effects = base_prompt_template.format(user_input=user_input, effect_summary="")
        base_prompt_length = len(base_prompt_without_effects)
        
        # 初始化 batches 变量
        batches = []
        
        # 如果只使用名称，按名称列表分割；如果使用完整描述，按科学效应分割
        if effect_names_only:
            # 只使用名称时，按名称列表分割
            names_list = [line.strip() for line in effect_summary.split('\n') if line.strip() and not line.strip().startswith('科学效应列表')]
            if not names_list:
                # 如果没有名称，返回错误
                return "无法获取科学效应名称列表"
            
            available_length = max_chars_per_batch - base_prompt_length
            
            # 按名称分批
            current_batch_names = []
            
            for name_line in names_list:
                # 测试添加这个名称后是否超过限制
                test_names = current_batch_names + [name_line]
                test_effect_summary = "\n".join(test_names)
                test_prompt = base_prompt_template.format(user_input=user_input, effect_summary=test_effect_summary)
                if len(test_prompt) > max_chars_per_batch and current_batch_names:
                    # 当前批次已满，保存并开始新批次
                    batches.append("\n".join(current_batch_names))
                    current_batch_names = [name_line]
                else:
                    current_batch_names.append(name_line)
            
            # 添加最后一个批次
            if current_batch_names:
                batches.append("\n".join(current_batch_names))
        else:
            # 使用完整描述时，将科学效应按段落分割（每个科学效应的详细解释以【开头）
            # 先找到"详细解释"部分的位置
            detail_start_marker = "详细解释（共"
            detail_start_idx = effect_summary.find(detail_start_marker)
            
            if detail_start_idx > 0:
                effect_list_part = effect_summary[:detail_start_idx].strip()
                effect_details_part = effect_summary[detail_start_idx:].strip()
            else:
                effect_list_part = ""
                effect_details_part = effect_summary
            
            # 计算可用长度（减去基础提示词长度）
            available_length = max_chars_per_batch - base_prompt_length
            
            # 如果总长度不超过限制，直接处理
            total_effect_length = len(effect_list_part) + len(effect_details_part) if effect_details_part else len(effect_list_part)
            if total_effect_length <= available_length:
                batches = [effect_summary]
            else:
                # 需要分批处理
                # 按科学效应分割（每个科学效应以【开头）
                import re
                # 使用正则表达式找到每个科学效应的开始位置
                effect_pattern = r'\n\n【\d+\.'
                effect_matches = list(re.finditer(effect_pattern, effect_details_part)) if effect_details_part else []
                
                if not effect_matches:
                    # 如果没有找到科学效应分隔符，按字符数简单分割
                    if not effect_details_part:
                        # 如果没有详细内容，使用整个摘要
                        batches = [effect_summary]
                    else:
                        batches = []
                        start = 0
                        while start < len(effect_details_part):
                            end = min(start + available_length - len(effect_list_part), len(effect_details_part))
                            batch_text = effect_list_part + "\n\n" + effect_details_part[start:end] if effect_list_part else effect_details_part[start:end]
                            batches.append(batch_text)
                            start = end
                        # 确保至少有一个批次
                        if not batches:
                            batches = [effect_summary]
                else:
                    # 按科学效应分割
                    batches = []
                    current_batch_text = effect_list_part if effect_list_part else ""
                    
                    for i, match in enumerate(effect_matches):
                        effect_start = match.start()
                        # 获取当前科学效应的完整文本（到下一个科学效应或结尾）
                        if i + 1 < len(effect_matches):
                            effect_end = effect_matches[i + 1].start()
                        else:
                            effect_end = len(effect_details_part)
                        
                        effect_text = effect_details_part[effect_start:effect_end]
                        
                        # 检查添加这个科学效应后是否超过限制
                        test_batch = current_batch_text + "\n\n" + effect_text if current_batch_text else effect_text
                        if len(test_batch) > available_length and current_batch_text:
                            # 当前批次已满，保存并开始新批次
                            batches.append(current_batch_text)
                            current_batch_text = effect_list_part + "\n\n" + effect_text if effect_list_part else effect_text
                        else:
                            # 添加到当前批次
                            if current_batch_text:
                                current_batch_text += "\n\n" + effect_text
                            else:
                                current_batch_text = effect_text
                    
                    # 添加最后一个批次
                    if current_batch_text:
                        batches.append(current_batch_text)
        
        # 检查 batches 是否为空
        if not batches:
            return "无法生成科学效应批次，请检查科学效应数据"
        
        # 处理每个批次
        batch_responses = []
        for i, batch_text in enumerate(batches):
            # 根据是否只使用名称，构建不同的批次提示词
            if effect_names_only:
                prompt = base_prompt_template.format(
                    user_input=user_input,
                    effect_summary=f"（第{i+1}批，共{len(batches)}批）\n{batch_text}"
                )
            else:
                prompt = base_prompt_template.format(
                    user_input=user_input,
                    effect_summary=f"（第{i+1}批，共{len(batches)}批）\n{batch_text}"
                )
            
            messages = [{"role": "user", "content": prompt}]
            
            
            if model == 'deepseek-reasoner':
                response_text, error = call_deepseek(messages, model="deepseek-reasoner")
                # 如果reasoner模型超时，改用chat模型重试一次
                if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
                    print(f"Reasoner模型超时（第{i+1}批），改用chat模型重试...")
                    response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
            else:
                response_text, error = call_deepseek(messages, model="deepseek-reasoner")
                # 如果reasoner模型超时，改用chat模型重试一次
                if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
                    print(f"Reasoner模型超时（第{i+1}批），改用chat模型重试...")
                    response_text, error = call_deepseek(messages, model="deepseek-chat", retry_with_split=False)
            
            if error:
                return f"生成解决方案时出错（第{i+1}批）: {error}"
            
            batch_responses.append({
                'batch_num': i + 1,
                'total_batches': len(batches),
                'response': response_text
            })
        
        # 检查是否有响应
        if not batch_responses:
            return "无法生成科学效应解决方案"
        
        # 组合所有批次的响应
        if len(batch_responses) == 1:
            return batch_responses[0]['response']
        
        # 如果有多个批次，使用reasoner模型组合所有结果
        combined_responses_text = ""
        for br in batch_responses:
            combined_responses_text += f"\n\n=== 第{br['batch_num']}批分析结果 ===\n{br['response']}\n"
        
        combine_prompt = f"""#role 你是一个TRIZ专家，负责整合多个科学效应分析结果

#问题描述：{user_input}

#各批次分析结果（共{len(batch_responses)}批）：{combined_responses_text}

**任务要求**：
1. 整合所有批次的分析结果，形成一个完整的解决方案
2. 识别不同批次中提到的相同或相关的科学效应，进行合并和优化
3. 优先考虑跨批次的科学效应组合方案，这些组合往往能产生更创新、更有效的解决方案
4. 确保最终方案覆盖所有相关的科学效应
5. 对于组合方案，要详细说明各个科学效应如何协同工作
6. 按照方案的重要性和创新性进行排序

请整合上述所有批次的分析结果，为问题提供最终的完整解决方案。"""
        
        combine_messages = [{"role": "user", "content": combine_prompt}]
        
        
        if model == 'deepseek-reasoner':
            final_response, error = call_deepseek(combine_messages, model="deepseek-reasoner")
            # 如果reasoner模型超时，改用chat模型重试一次
            if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
                print(f"Reasoner模型超时（组合阶段），改用chat模型重试...")
                final_response, error = call_deepseek(combine_messages, model="deepseek-chat", retry_with_split=False)
        else:
            final_response, error = call_deepseek(combine_messages, model="deepseek-reasoner")
            # 如果reasoner模型超时，改用chat模型重试一次
            if error and ('timeout' in error.lower() or 'timed out' in error.lower() or 'request timed out' in error.lower()):
                print(f"Reasoner模型超时（组合阶段），改用chat模型重试...")
                final_response, error = call_deepseek(combine_messages, model="deepseek-chat", retry_with_split=False)
        
        if error:
            # 如果组合失败，返回所有批次的原始响应
            return f"**注意：内容较长，已分批处理（共{len(batch_responses)}批）**\n\n" + combined_responses_text
        
        return final_response
    except Exception as e:
        error_msg = f"科学效应流程执行出错: {e}"
        log_error(error_msg, exception=e, context={'function': 'solve_with_science_effects', 'user_input': user_input[:100] if user_input else None})
        print(error_msg)
        import traceback
        traceback.print_exc()
        return error_msg

@app.route('/')
def index():
    """返回主页面"""
    return send_from_directory('static', 'index.html')

@app.route('/test-api')
def test_api():
    """返回API测试页面"""
    return send_from_directory('static', 'test-api.html')

def update_progress_message(session_id, progress_text):
    """
    更新进度消息（用于前端显示）
    :param session_id: 会话ID
    :param progress_text: 进度文本
    """
    # 这里可以存储进度信息，供前端查询
    # 由于Flask是同步的，我们将在响应中包含进度信息
    pass

@app.route('/api/chat', methods=['POST'])
def chat():
    """处理聊天请求，集成TRIZ矛盾解题流程和科学效应解题流程"""
    data = request.json
    message = data.get('message', '')
    model = data.get('model', 'deepseek-chat')
    session_id = data.get('session_id', 'default')
    
    if not message:
        return jsonify({'error': '消息不能为空'}), 400
    
    # 获取历史对话
    history = get_conversation_history(session_id)
    
    # 添加用户消息到历史
    add_to_history(session_id, "user", message)
    
    # 使用chat模型（优先使用deepseek-chat，如果没有则使用当前选择的模型）
    check_model = 'deepseek-chat' if deepseek_client else model
    
    # 存储进度信息
    progress_steps = []
    
    # 追踪所有调用过的模型
    used_models = set()
    used_models.add(check_model)  # chat模型用于检查矛盾、提取参数等
    
    response_text = ""
    triz_info = None
    science_effect_info = None
    
    # 第一步：优先检查技术矛盾（矛盾解题流程）
    progress_steps.append("🔍 步骤1/5: 正在检测是否存在技术矛盾...")
    has_contradiction, contradiction_result, contradiction_type = check_contradiction(message, check_model)
    
    if has_contradiction:
        # 确定矛盾类型，默认为硬件矛盾
        if contradiction_type is None:
            contradiction_type = 'hardware'
        
        contradiction_type_name = "软件" if contradiction_type == 'software' else "硬件"
        progress_steps.append(f"✅ 检测到{contradiction_type_name}技术矛盾，启动TRIZ矛盾解题流程")
        progress_steps.append("🔍 步骤2/5: 正在提炼改善参数和恶化参数...")
        # 启动TRIZ矛盾解题流程
        try:
            # 第二步：提炼改善和恶化的参数（尝试提取多个）
            contradictions = extract_parameters(message, check_model, extract_multiple=True, progress_steps=progress_steps, contradiction_type=contradiction_type)
            
            if contradictions and len(contradictions) > 0:
                # 为每个矛盾添加矛盾类型
                for contradiction in contradictions:
                    if 'contradiction_type' not in contradiction:
                        contradiction['contradiction_type'] = contradiction_type
                
                # 如果有多个矛盾组合，返回选择请求
                if len(contradictions) > 1:
                    contradiction_type_name = "软件" if contradiction_type == 'software' else "硬件"
                    return jsonify({
                        'requires_selection': True,
                        'selection_type': 'contradictions',
                        'options': contradictions,
                        'message': message,
                        'progress': progress_steps,
                        'prompt': f'检测到多个{contradiction_type_name}技术矛盾组合，请选择要分析的一个或多个矛盾：'
                    })
                
                # 只有一个矛盾，直接处理
                contradiction = contradictions[0]
                # 确保矛盾类型已设置
                if 'contradiction_type' not in contradiction:
                    contradiction['contradiction_type'] = contradiction_type
                else:
                    contradiction_type = contradiction.get('contradiction_type', contradiction_type)
                
                improve_param = contradiction.get('improve_param')
                worsen_param = contradiction.get('worsen_param')
                
                if improve_param and worsen_param:
                    # 根据矛盾类型选择参数列表
                    if contradiction_type == 'software':
                        param_list = SOFTWARE_PARAMETERS
                    else:
                        param_list = TRIZ_PARAMETERS
                    progress_steps.append(f"✅ 改善参数: {param_list[improve_param-1]}, 恶化参数: {param_list[worsen_param-1]}")
                    progress_steps.append("🔍 步骤3/5: 正在查询矛盾矩阵...")
                    # 第三步：查询矛盾矩阵获取发明原则编号
                    principle_nums = get_contradiction_matrix(improve_param, worsen_param, contradiction_type=contradiction_type)
                    valid_principles = [p for p in principle_nums if p != 0]
                    progress_steps.append(f"✅ 查询到 {len(valid_principles)} 个发明原则: {', '.join([f'原则{p}' for p in valid_principles])}")
                    progress_steps.append("🔍 步骤4/5: 正在读取发明原则PDF文件...")
                    # 第四步：读取PDF文件获取原则描述
                    principle_descriptions = get_principle_descriptions(principle_nums)
                    progress_steps.append(f"✅ 已读取 {len(principle_descriptions)} 个发明原则的详细描述")
                    progress_steps.append("🔍 步骤5/5: 正在使用reasoner模型生成解决方案...")
                    # 第五步：使用reasoner模型生成解决方案
                    reasoner_model = 'deepseek-reasoner' if deepseek_client else model
                    used_models.add(reasoner_model)  # 追踪reasoner模型
                    solution = solve_with_triz(message, principle_descriptions, reasoner_model, progress_steps=progress_steps)
                    progress_steps.append("✅ 已完成分析，生成解决方案")
                    
                    # 构建响应
                    response_text = f"""检测到{contradiction_type_name}技术矛盾，已启动TRIZ矛盾解题流程：

**改善参数**: {param_list[improve_param-1]}
**恶化参数**: {param_list[worsen_param-1]}

**推荐的发明原则**:
"""
                    for p in principle_descriptions:
                        response_text += f"\n原则{p['number']}: {p['name']}\n"
                    
                    response_text += f"\n**解决方案**:\n{solution}"
                    
                    triz_info = {
                        "has_contradiction": True,
                        "improve_param": improve_param,
                        "worsen_param": worsen_param,
                        "principle_numbers": principle_nums,
                        "principle_descriptions": principle_descriptions
                    }
                else:
                    # 参数提取失败，尝试科学效应流程
                    progress_steps.append("⚠️ 参数提取失败，尝试科学效应解题流程...")
                    triz_info = {"has_contradiction": True, "extraction_failed": True}
            else:
                # 兼容旧的单参数提取方式
                improve_param, worsen_param = extract_parameters(message, check_model, extract_multiple=False, progress_steps=progress_steps, contradiction_type=contradiction_type)
                if improve_param and worsen_param:
                    # 根据矛盾类型选择参数列表
                    if contradiction_type == 'software':
                        param_list = SOFTWARE_PARAMETERS
                    else:
                        param_list = TRIZ_PARAMETERS
                    progress_steps.append(f"✅ 改善参数: {param_list[improve_param-1]}, 恶化参数: {param_list[worsen_param-1]}")
                    progress_steps.append("🔍 步骤3/5: 正在查询矛盾矩阵...")
                    principle_nums = get_contradiction_matrix(improve_param, worsen_param, contradiction_type=contradiction_type)
                    valid_principles = [p for p in principle_nums if p != 0]
                    progress_steps.append(f"✅ 查询到 {len(valid_principles)} 个发明原则: {', '.join([f'原则{p}' for p in valid_principles])}")
                    progress_steps.append("🔍 步骤4/5: 正在读取发明原则PDF文件...")
                    principle_descriptions = get_principle_descriptions(principle_nums)
                    progress_steps.append(f"✅ 已读取 {len(principle_descriptions)} 个发明原则的详细描述")
                    progress_steps.append("🔍 步骤5/5: 正在使用reasoner模型生成解决方案...")
                    reasoner_model = 'deepseek-reasoner' if deepseek_client else model
                    used_models.add(reasoner_model)  # 追踪reasoner模型
                    solution = solve_with_triz(message, principle_descriptions, reasoner_model, progress_steps=progress_steps)
                    progress_steps.append("✅ 已完成分析，生成解决方案")
                    
                    response_text = f"""检测到{contradiction_type_name}技术矛盾，已启动TRIZ矛盾解题流程：

**改善参数**: {param_list[improve_param-1]}
**恶化参数**: {param_list[worsen_param-1]}

**推荐的发明原则**:
"""
                    for p in principle_descriptions:
                        response_text += f"\n原则{p['number']}: {p['name']}\n"
                    
                    response_text += f"\n**解决方案**:\n{solution}"
                    
                    triz_info = {
                        "has_contradiction": True,
                        "contradiction_type": contradiction_type,
                        "improve_param": improve_param,
                        "worsen_param": worsen_param,
                        "principle_numbers": principle_nums,
                        "principle_descriptions": principle_descriptions
                    }
                else:
                    progress_steps.append("⚠️ 参数提取失败，尝试科学效应解题流程...")
                    triz_info = {"has_contradiction": True, "contradiction_type": contradiction_type, "extraction_failed": True}
        except Exception as e:
            # TRIZ流程出错，尝试科学效应流程
            error_msg = f"矛盾解题流程执行出错: {str(e)}"
            log_error(error_msg, exception=e, context={'step': 'contradiction_solving', 'message': message})
            progress_steps.append(f"⚠️ {error_msg}，尝试科学效应解题流程...")
            triz_info = {"has_contradiction": True, "error": str(e)}
    
    # 如果没有矛盾或矛盾流程失败，尝试科学效应解题流程
    if not response_text:
        # 清空之前的进度（如果矛盾流程失败）
        if progress_steps and not progress_steps[-1].startswith("🔍 步骤1/5"):
            progress_steps = []
        progress_steps.append("🔍 步骤1/5: 正在检测是否存在功能问题...")
        # 判断是否存在有问题的功能（科学效应流程）
        has_function_problem, function_problem_result = check_function_problem(message, check_model, progress_steps=progress_steps)
        
        if has_function_problem:
            # 启动科学效应解题流程
            try:
                progress_steps.append("✅ 检测到功能问题，启动科学效应解题流程")
                progress_steps.append("🔍 步骤2/5: 正在提炼问题功能...")
                # 第二步：提炼存在问题的功能（尝试提取多个）
                functions = extract_function(message, check_model, extract_multiple=True, progress_steps=progress_steps)
                
                if functions and len(functions) > 0:
                    # 验证所有功能是否都在数据库中（从文件名列表验证）
                    function_list = get_function_list()
                    parameter_list = get_parameter_list()
                    transform_list = get_transform_list()
                    all_valid_functions = set(function_list + parameter_list + transform_list)
                    
                    # 过滤掉不在数据库中的功能
                    valid_functions = []
                    for func in functions:
                        function_name = func.get('function_name')
                        category = func.get('category')
                        # 验证功能名称是否在对应的列表中
                        if category == 'function' and function_name in function_list:
                            valid_functions.append(func)
                        elif category == 'parameter' and function_name in parameter_list:
                            valid_functions.append(func)
                        elif category == 'transform' and function_name in transform_list:
                            valid_functions.append(func)
                        # 如果不在任何列表中，跳过（不添加自定义功能）
                    
                    functions = valid_functions
                    
                    if len(functions) == 0:
                        # 所有功能都不在数据库中，回退到普通对话
                        progress_steps.append("⚠️ 提取的功能不在数据库中，回退到普通对话模式")
                        # 继续普通对话流程
                    else:
                        # 按优先级排序，主要功能优先
                        functions.sort(key=lambda x: (
                            not x.get('is_primary', False),  # 主要功能优先
                            x.get('priority', 999)  # 然后按priority排序
                        ))
                    
                    # 如果有多个功能问题，返回选择请求（主要功能默认选中）
                    if len(functions) > 1:
                        return jsonify({
                            'requires_selection': True,
                            'selection_type': 'functions',
                            'options': functions,
                            'message': message,
                            'progress': progress_steps,
                            'prompt': '检测到多个功能问题，已识别主要功能（已默认选中），请选择要分析的一个或多个功能：',
                            'default_selected': [0] if functions[0].get('is_primary', False) else []
                        })
                    
                    # 只有一个功能，直接处理（优先处理主要功能）
                    function = functions[0]
                    function_name = function.get('function_name')
                    category = function.get('category')
                    
                    # 如果是主要功能，在进度中标注
                    if function.get('is_primary', False):
                        progress_steps.append(f"✅ 已识别主要功能问题: {function_name} ({category})")
                    else:
                        progress_steps.append(f"✅ 已识别功能: {function_name} ({category})")
                    
                    if function_name and category:
                        progress_steps.append(f"✅ 已识别功能: {function_name} ({category})")
                        progress_steps.append("🔍 步骤3/5: 正在查找并读取科学效应文件...")
                        # 第三步：优先从数据库读取，如果没有则从文件读取
                        html_path = find_effect_file(function_name, category)
                        effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
                        
                        if effect_summary:
                            original_count = len(effect_summary.split('【'))-1 if '【' in effect_summary else 0
                            progress_steps.append(f"✅ 已读取科学效应，共包含 {original_count} 个科学效应")
                            progress_steps.append("🔍 步骤4/5: 正在使用reasoner模型分析科学效应...")
                            # 第四步：使用reasoner模型生成解决方案
                            reasoner_model = 'deepseek-reasoner' if deepseek_client else model
                            used_models.add(reasoner_model)  # 追踪reasoner模型
                            solution = solve_with_science_effects(message, html_path=html_path, function_name=function_name, category=category, model=reasoner_model, progress_steps=progress_steps)
                            progress_steps.append("✅ 步骤5/5: 已完成分析，生成解决方案")
                            
                            # 获取科学效应摘要用于显示（根据数量决定使用完整描述还是名称）
                            parsed_data = parse_effect_html(html_path=html_path, function_name=function_name, category=category)
                            filtered_effect_summary = effect_summary  # 默认使用原始摘要
                            if parsed_data and parsed_data.get('effect_list'):
                                effect_count = len(parsed_data['effect_list'])
                                if effect_count > 30:
                                    # 数量>30，只使用名称列表
                                    effect_names = [effect['name'] for effect in parsed_data['effect_list']]
                                    filtered_effect_summary = f"科学效应列表（共{len(effect_names)}个）：\n"
                                    for i, name in enumerate(effect_names, 1):
                                        filtered_effect_summary += f"{i}. {name}\n"
                                else:
                                    # 数量<=30，使用完整描述
                                    filtered_effect_summary = effect_summary
                            
                            # 构建响应（显示筛选后的科学效应）
                                response_text = f"""检测到功能问题，已启动TRIZ科学效应解题流程：

**问题功能**: {function_name} ({category})

**相关科学效应**:
{filtered_effect_summary}

**推荐解决方案**:
{solution}"""
                                
                                science_effect_info = {
                                    "has_function_problem": True,
                                    "function_name": function_name,
                                    "category": category,
                                    "effect_summary": effect_summary
                                }
                            else:
                                response_text = f"检测到功能问题：{function_name}，但无法读取科学效应内容。"
                                science_effect_info = {"has_function_problem": True, "function_name": function_name, "read_failed": True}
                        else:
                            response_text = f"检测到功能问题，但未找到对应的科学效应文件：{function_name}.html"
                            science_effect_info = {"has_function_problem": True, "function_name": function_name, "file_not_found": True}
                    else:
                        # 功能提取失败，尝试旧的单功能提取方式
                        function_name, category = extract_function(message, check_model, extract_multiple=False, progress_steps=progress_steps)
                        if function_name and category:
                            # 继续处理单个功能（递归调用，但避免无限循环）
                            progress_steps.append(f"✅ 已识别功能: {function_name} ({category})")
                            progress_steps.append("🔍 步骤3/5: 正在查找并读取科学效应文件...")
                            html_path = find_effect_file(function_name, category)
                            
                            # 优先从数据库读取，如果没有则从文件读取
                            html_path = find_effect_file(function_name, category)
                            effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
                            
                            if effect_summary:
                                original_count = len(effect_summary.split('【'))-1 if '【' in effect_summary else 0
                                progress_steps.append(f"✅ 已读取科学效应，共包含 {original_count} 个科学效应")
                                progress_steps.append("🔍 步骤3.5/5: 正在使用chat模型筛选科学效应...")
                                progress_steps.append("🔍 步骤4/5: 正在使用reasoner模型分析科学效应...")
                                reasoner_model = 'deepseek-reasoner' if deepseek_client else model
                                used_models.add(reasoner_model)  # 追踪reasoner模型
                                solution = solve_with_science_effects(message, html_path=html_path, function_name=function_name, category=category, model=reasoner_model, progress_steps=progress_steps)
                                progress_steps.append("✅ 步骤5/5: 已完成分析，生成解决方案")
                                
                                # 获取科学效应摘要用于显示（根据数量决定使用完整描述还是名称）
                                parsed_data = parse_effect_html(html_path=html_path, function_name=function_name, category=category)
                                filtered_effect_summary = effect_summary  # 默认使用原始摘要
                                if parsed_data and parsed_data.get('effect_list'):
                                    effect_count = len(parsed_data['effect_list'])
                                    if effect_count > 30:
                                        # 数量>30，只使用名称列表
                                        effect_names = [effect['name'] for effect in parsed_data['effect_list']]
                                        filtered_effect_summary = f"科学效应列表（共{len(effect_names)}个）：\n"
                                        for i, name in enumerate(effect_names, 1):
                                            filtered_effect_summary += f"{i}. {name}\n"
                                    else:
                                        # 数量<=30，使用完整描述
                                        filtered_effect_summary = effect_summary
                                
                                response_text = f"""检测到功能问题，已启动TRIZ科学效应解题流程：

**问题功能**: {function_name} ({category})

**相关科学效应**:
{filtered_effect_summary}

**推荐解决方案**:
{solution}"""
                                
                                science_effect_info = {
                                    "has_function_problem": True,
                                    "function_name": function_name,
                                    "category": category,
                                    "effect_summary": effect_summary
                                }
                        else:
                            # 功能提取失败，使用普通对话
                            response_text = f"检测到功能问题，但功能提取失败。\n问题分析：{function_problem_result}\n\n继续普通对话模式..."
                            science_effect_info = {"has_function_problem": True, "extraction_failed": True}
                else:
                    # 功能提取失败，尝试旧的单功能提取方式
                    function_name, category = extract_function(message, check_model, extract_multiple=False)
                    if function_name and category:
                        progress_steps.append(f"✅ 已识别功能: {function_name} ({category})")
                        progress_steps.append("🔍 步骤3/5: 正在查找并读取科学效应文件...")
                        # 优先从数据库读取，如果没有则从文件读取
                        html_path = find_effect_file(function_name, category)
                        effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
                        
                        if effect_summary:
                            original_count = len(effect_summary.split('【'))-1 if '【' in effect_summary else 0
                            progress_steps.append(f"✅ 已读取科学效应，共包含 {original_count} 个科学效应")
                            progress_steps.append("🔍 步骤4/5: 正在使用reasoner模型分析科学效应...")
                            reasoner_model = 'deepseek-reasoner' if deepseek_client else model
                            used_models.add(reasoner_model)  # 追踪reasoner模型
                            solution = solve_with_science_effects(message, html_path=html_path, function_name=function_name, category=category, model=reasoner_model, progress_steps=progress_steps)
                            progress_steps.append("✅ 步骤5/5: 已完成分析，生成解决方案")
                            
                            # 获取科学效应摘要用于显示（根据数量决定使用完整描述还是名称）
                            parsed_data = parse_effect_html(html_path=html_path, function_name=function_name, category=category)
                            filtered_effect_summary = effect_summary  # 默认使用原始摘要
                            if parsed_data and parsed_data.get('effect_list'):
                                effect_count = len(parsed_data['effect_list'])
                                if effect_count > 30:
                                    # 数量>30，只使用名称列表
                                    effect_names = [effect['name'] for effect in parsed_data['effect_list']]
                                    filtered_effect_summary = f"科学效应列表（共{len(effect_names)}个）：\n"
                                    for i, name in enumerate(effect_names, 1):
                                        filtered_effect_summary += f"{i}. {name}\n"
                                else:
                                    # 数量<=30，使用完整描述
                                    filtered_effect_summary = effect_summary
                            
                            response_text = f"""检测到功能问题，已启动TRIZ科学效应解题流程：

**问题功能**: {function_name} ({category})

**相关科学效应**:
{filtered_effect_summary}

**推荐解决方案**:
{solution}"""
                            
                            science_effect_info = {
                                "has_function_problem": True,
                                "function_name": function_name,
                                "category": category,
                                "effect_summary": effect_summary
                            }
                    else:
                        # 功能提取失败，使用普通对话
                        response_text = f"检测到功能问题，但功能提取失败。\n问题分析：{function_problem_result}\n\n继续普通对话模式..."
                        science_effect_info = {"has_function_problem": True, "extraction_failed": True}
            except Exception as e:
                # 科学效应流程出错，回退到普通对话
                error_msg = f"科学效应流程执行出错: {str(e)}"
                log_error(error_msg, exception=e, context={'step': 'science_effect_solving', 'message': message})
                response_text = f"{error_msg}\n\n继续普通对话模式..."
                science_effect_info = {"has_function_problem": True, "error": str(e)}
    
    # 如果没有矛盾或TRIZ流程失败，使用普通对话模式
    if not response_text:
        # 清空之前的进度（如果TRIZ流程失败）
        if progress_steps and not progress_steps[-1].startswith("🔍 正在处理"):
            progress_steps = []
        progress_steps.append("🔍 正在处理您的消息...")
    # 构建消息列表
    messages = []
    for h in history:
        messages.append({"role": h["role"], "content": h["content"]})
    
    # 根据选择的模型调用相应的API
    error = None
    used_models.add(model)  # 追踪普通对话模式使用的模型
    
    if model == 'deepseek-chat':
        response_text, error = call_deepseek(messages, model="deepseek-chat")
    elif model == 'deepseek-reasoner':
        response_text, error = call_deepseek(messages, model="deepseek-reasoner")
    else:
        error = f"不支持的模型: {model}"
    
    if error:
        log_error(f"普通对话模式错误: {error}", context={'model': model, 'message': message[:100] if message else None})
        return jsonify({'error': error}), 500
    
    # 普通对话模式完成
    if progress_steps:
        progress_steps.append("✅ 已完成处理")
    
    # 添加助手回复到历史
    add_to_history(session_id, "assistant", response_text)
    
    result = {
        'response': response_text,
        'model': model,
        'models': list(used_models)  # 返回所有使用过的模型列表
    }
    
    if triz_info:
        result['triz_info'] = triz_info
    
    if science_effect_info:
        result['science_effect_info'] = science_effect_info
    
    # 添加进度信息
    if progress_steps:
        result['progress'] = progress_steps
    
    return jsonify(result)

@app.route('/api/process-selection', methods=['POST'])
def process_selection():
    """处理用户选择的矛盾或功能问题，逐个分析并拼接结果"""
    data = request.json
    selection_type = data.get('selection_type')  # 'contradictions' 或 'functions'
    selected_indices = data.get('selected_indices', [])  # 用户选择的索引列表
    options = data.get('options', [])  # 选项列表
    message = data.get('message', '')
    model = data.get('model', 'deepseek-chat')
    session_id = data.get('session_id', 'default')
    
    if not selected_indices or not options:
        error_msg = '请至少选择一个选项'
        log_error(error_msg, context={'selection_type': selection_type, 'selected_indices': selected_indices})
        return jsonify({'error': error_msg}), 400
    
    # 使用chat模型（优先使用deepseek-chat，如果没有则使用当前选择的模型）
    check_model = 'deepseek-chat' if deepseek_client else model
    reasoner_model = 'deepseek-reasoner' if deepseek_client else model
    
    # 追踪所有调用过的模型
    used_models = set()
    used_models.add(check_model)  # chat模型用于提取参数等
    used_models.add(reasoner_model)  # reasoner模型用于生成解决方案
    
    all_results = []
    all_progress = []
    
    # 逐个处理选中的选项
    for idx, option_idx in enumerate(selected_indices):
        if option_idx >= len(options):
            continue
        
        option = options[option_idx]
        progress_steps = []
        
        if selection_type == 'contradictions':
            # 处理矛盾
            improve_param = option.get('improve_param')
            worsen_param = option.get('worsen_param')
            improve_name = option.get('improve_param_name', '')
            worsen_name = option.get('worsen_param_name', '')
            contradiction_type = option.get('contradiction_type', 'hardware')  # 从选项中获取矛盾类型
            
            # 根据矛盾类型选择参数列表
            if contradiction_type == 'software':
                param_list = SOFTWARE_PARAMETERS
            else:
                param_list = TRIZ_PARAMETERS
            
            # 如果参数编号存在，验证并获取参数名称
            if improve_param and improve_param >= 1 and improve_param <= len(param_list):
                improve_name = param_list[improve_param - 1]
            elif improve_name:
                # 尝试从参数名称匹配到参数编号
                for i, param in enumerate(param_list):
                    if improve_name.lower() in param.lower() or param.lower() in improve_name.lower():
                        improve_param = i + 1
                        improve_name = param
                        break
            
            if worsen_param and worsen_param >= 1 and worsen_param <= len(param_list):
                worsen_name = param_list[worsen_param - 1]
            elif worsen_name:
                # 尝试从参数名称匹配到参数编号
                for i, param in enumerate(param_list):
                    if worsen_name.lower() in param.lower() or param.lower() in worsen_name.lower():
                        worsen_param = i + 1
                        worsen_name = param
                        break
            
            # 如果仍然没有参数编号，尝试使用提取函数
            if not improve_param or not worsen_param:
                custom_message = f"改善参数：{improve_name or '未知'}，恶化参数：{worsen_name or '未知'}"
                extracted_improve, extracted_worsen = extract_parameters(custom_message, check_model, extract_multiple=False, progress_steps=progress_steps, contradiction_type=contradiction_type)
                if extracted_improve and extracted_worsen:
                    improve_param = extracted_improve
                    worsen_param = extracted_worsen
                    improve_name = param_list[improve_param - 1]
                    worsen_name = param_list[worsen_param - 1]
            
            # 如果仍然没有参数编号，跳过这个矛盾
            if not improve_param or not worsen_param:
                progress_steps.append(f"⚠️ 矛盾 {idx+1}: 无法识别参数，跳过")
                all_progress.extend(progress_steps)
                continue
            
            contradiction_type_name = "软件" if contradiction_type == 'software' else "硬件"
            progress_steps.append(f"🔍 分析{contradiction_type_name}矛盾 {idx+1}/{len(selected_indices)}: {improve_name} vs {worsen_name}")
            
            if improve_param and worsen_param:
                # 查询矛盾矩阵
                principle_nums = get_contradiction_matrix(improve_param, worsen_param, contradiction_type=contradiction_type)
                valid_principles = [p for p in principle_nums if p != 0]
                progress_steps.append(f"✅ 查询到 {len(valid_principles)} 个发明原则")
                
                # 读取原则描述
                principle_descriptions = get_principle_descriptions(principle_nums)
                progress_steps.append(f"✅ 已读取 {len(principle_descriptions)} 个发明原则的详细描述")
                
                # 生成解决方案
                solution = solve_with_triz(message, principle_descriptions, reasoner_model, progress_steps=progress_steps)
                progress_steps.append("✅ 已完成分析")
                
                result_text = f"""\n\n=== {contradiction_type_name}矛盾 {idx+1}: {improve_name} vs {worsen_name} ===\n\n"""
                result_text += f"**改善参数**: {improve_name}\n"
                result_text += f"**恶化参数**: {worsen_name}\n\n"
                result_text += f"**推荐的发明原则**:\n"
                for p in principle_descriptions:
                    result_text += f"\n原则{p['number']}: {p['name']}\n"
                result_text += f"\n**解决方案**:\n{solution}\n"
                
                all_results.append(result_text)
                all_progress.extend(progress_steps)
            else:
                # 如果无法匹配到参数编号，跳过这个矛盾
                progress_steps.append(f"⚠️ 矛盾 {idx+1}: 无法识别参数，跳过")
                all_progress.extend(progress_steps)
        
        elif selection_type == 'functions':
            # 处理功能问题
            function_name = option.get('function_name')
            category = option.get('category')
            description = option.get('description', '')
            
            # 验证功能是否在数据库中（从文件名列表验证）
            function_list = get_function_list()
            parameter_list = get_parameter_list()
            transform_list = get_transform_list()
            
            is_valid = False
            if category == 'function' and function_name in function_list:
                is_valid = True
            elif category == 'parameter' and function_name in parameter_list:
                is_valid = True
            elif category == 'transform' and function_name in transform_list:
                is_valid = True
            
            if not is_valid:
                progress_steps.append(f"⚠️ 功能问题 {idx+1}: {function_name} ({category}) 不在数据库中，跳过")
                all_progress.extend(progress_steps)
                continue
            
            progress_steps.append(f"🔍 分析功能问题 {idx+1}/{len(selected_indices)}: {function_name} ({category})")
            
            if function_name and category:
                # 优先从数据库读取，如果没有则从文件读取
                html_path = find_effect_file(function_name, category)
                effect_summary = get_effect_summary(html_path=html_path, function_name=function_name, category=category)
                
                if effect_summary:
                    progress_steps.append(f"✅ 已读取科学效应")
                    
                    # 生成解决方案
                    solution = solve_with_science_effects(message, html_path=html_path, function_name=function_name, category=category, model=reasoner_model, progress_steps=progress_steps)
                    progress_steps.append("✅ 已完成分析")
                    
                    # 获取科学效应摘要用于显示（根据数量决定使用完整描述还是名称）
                    parsed_data = parse_effect_html(html_path=html_path, function_name=function_name, category=category)
                    filtered_effect_summary = effect_summary  # 默认使用原始摘要
                    if parsed_data and parsed_data.get('effect_list'):
                        effect_count = len(parsed_data['effect_list'])
                        if effect_count > 30:
                            # 数量>30，只使用名称列表
                            effect_names = [effect['name'] for effect in parsed_data['effect_list']]
                            filtered_effect_summary = f"科学效应列表（共{len(effect_names)}个）：\n"
                            for i, name in enumerate(effect_names, 1):
                                filtered_effect_summary += f"{i}. {name}\n"
                        else:
                            # 数量<=30，使用完整描述
                            filtered_effect_summary = effect_summary
                    
                    result_text = f"""\n\n=== 功能问题 {idx+1}: {function_name} ({category}) ===\n\n"""
                    if description:
                        result_text += f"**问题描述**: {description}\n\n"
                    result_text += f"**相关科学效应**:\n{filtered_effect_summary}\n\n"
                    result_text += f"**推荐解决方案**:\n{solution}\n"
                    
                    all_results.append(result_text)
                    all_progress.extend(progress_steps)
                else:
                    # 如果无法读取科学效应内容，报错（不再支持自定义功能）
                    result_text = f"\n\n=== 功能问题 {idx+1}: {function_name} ({category}) ===\n\n**错误**: 无法读取科学效应内容\n"
                    all_results.append(result_text)
                    all_progress.extend(progress_steps)
            else:
                # 如果找不到HTML文件，报错（不再支持自定义功能）
                result_text = f"\n\n=== 功能问题 {idx+1}: {function_name} ({category}) ===\n\n**错误**: 未找到对应的科学效应文件\n"
                all_results.append(result_text)
                all_progress.extend(progress_steps)
    
    # 拼接所有结果
    if len(all_results) == 1:
        final_response = f"检测到{'技术矛盾' if selection_type == 'contradictions' else '功能问题'}，已启动TRIZ解题流程：{all_results[0]}"
    else:
        header = f"检测到{len(selected_indices)}个{'技术矛盾' if selection_type == 'contradictions' else '功能问题'}，已逐个分析："
        final_response = header + "\n".join(all_results)
    
    # 添加助手回复到历史
    add_to_history(session_id, "assistant", final_response)
    
    return jsonify({
        'response': final_response,
        'model': model,
        'models': list(used_models),  # 返回所有使用过的模型列表
        'progress': all_progress,
        'processed_count': len(all_results)
    })

@app.route('/api/models', methods=['GET'])
def get_models():
    """获取可用的模型列表"""
    models = []
    
    if deepseek_client:
        models.append({
            'id': 'deepseek-chat',
            'name': 'DeepSeek Chat',
            'available': True
        })
        models.append({
            'id': 'deepseek-reasoner',
            'name': 'DeepSeek Reasoner',
            'available': True
        })
    
    # 如果没有配置任何API密钥，返回示例模型
    if not models:
        models = [
            {'id': 'deepseek-chat', 'name': 'DeepSeek Chat', 'available': False},
            {'id': 'deepseek-reasoner', 'name': 'DeepSeek Reasoner', 'available': False}
        ]
    
    return jsonify({'models': models})

@app.route('/api/clear', methods=['POST'])
def clear_history():
    """清空对话历史"""
    data = request.json
    session_id = data.get('session_id', 'default')
    
    if session_id in conversations:
        conversations[session_id] = []
    
    return jsonify({'success': True})

if __name__ == '__main__':
    # 使用 threaded=True 和更好的配置，避免阻塞
    app.run(
        debug=False,  # 生产环境关闭debug模式，避免性能问题
        host='127.0.0.1',  # 只监听本地，更安全
        port=5000,
        threaded=True,  # 启用多线程，避免阻塞
        use_reloader=False  # 关闭自动重载，避免问题
    )
