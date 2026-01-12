from typing import Optional, Dict, Any, Literal
import os
import logging
import time
import requests
from dotenv import load_dotenv
from app.core.config import settings
from app.core.review_rules import ELECTRIC_REVIEW_RULES, GENERAL_REVIEW_PROMPT

# 加载环境变量
load_dotenv()

# 初始化日志
logger = logging.getLogger(__name__)

# 定义支持的模型类型（和接口参数对应）
ModelType = Literal["ernie", "qianwen"]

class AIService:
    """统一的AI服务接口，支持文心一言和通义千问，可指定模型或自动切换"""
    
    def __init__(self):
        # 模型配置（可扩展不同版本）
        self.model_configs = {
            "ernie": {
                "api_key": settings.ERNIE_API_KEY,
                "api_url": settings.ERNIE_API_URL,
                "timeout": 60,
                "default_model_version": "ernie-3.5-8k",
                "max_tokens_limit": 2048  # 新增：文心一言上限
            },
            "qianwen": {
                "api_key": settings.DASHSCOPE_API_KEY,
                "api_url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",  # 千问正确地址
                "timeout": 60,
                "default_model_version": "qwen-turbo",
                "max_tokens_limit": 8192  # 千问上限
            }
        }
        
        # 过滤掉未正确配置的模型，生成可用模型列表
        self.available_models = [
            model_name for model_name, config in self.model_configs.items()
            if config["api_key"] and config["api_url"]
        ]
        
        if not self.available_models:
            raise ValueError("没有可用的AI模型，请检查.env中的API Key和URL配置")
        
        logger.info(f"已加载可用模型：{self.available_models}")

    def call_ai(
        self, 
        prompt: str, 
        model_name: Optional[ModelType] = None,  # 新增：指定模型名称
        temperature: float = 0.3, 
        max_tokens: int = 2048,  # 修正：默认降到2048
        model_version: Optional[str] = None  # 新增：指定模型版本
    ) -> Dict[str, Any]:
        """
        统一调用AI模型的接口
        :param prompt: 提示词
        :param model_name: 指定调用的模型（ernie/qianwen），None则自动重试所有可用模型
        :param temperature: 生成温度
        :param max_tokens: 最大生成token数
        :param model_version: 模型版本（如ernie-4.0、qwen-plus），None使用默认版本
        :return: 包含status、content和model_used的字典
        """


        rule_prompts = {
            "wire_color": ELECTRIC_REVIEW_RULES["wire_color"]["prompt"],
            "symbol_standard": ELECTRIC_REVIEW_RULES["symbol_standard"]["prompt"],
            "safety_distance": ELECTRIC_REVIEW_RULES["safety_distance"]["prompt"],
            "load_balance": ELECTRIC_REVIEW_RULES["load_balance"]["prompt"],
            "grounding_spec": ELECTRIC_REVIEW_RULES["grounding_spec"]["prompt"]
        }
    # 生成带5条规则的完整提示词
    final_prompt = GENERAL_REVIEW_PROMPT.format(**rule_prompts) + f"\n\n需审查的图纸相关信息：{prompt}"


        # 确定要尝试的模型列表
        target_models = []
        if model_name:
            # 1. 指定了具体模型：只尝试该模型（如果可用）
            if model_name not in self.available_models:
                err_msg = f"指定的模型{model_name}不可用（未配置或配置错误），可用模型：{self.available_models}"
                logger.error(err_msg)
                return {
                    "status": "failure",
                    "content": err_msg,
                    "model_used": None
                }
            target_models = [model_name]
        else:
            # 2. 未指定模型：按顺序重试所有可用模型
            target_models = self.available_models

        # 依次尝试目标模型
        for model_name in target_models:
            start_time = time.time()
            config = self.model_configs[model_name]
            
            # 新增：容错处理——max_tokens不超过模型上限
            final_max_tokens = min(max_tokens, config["max_tokens_limit"])
            if final_max_tokens != max_tokens:
                logger.warning(f"模型{model_name}的max_tokens超限，自动调整为{final_max_tokens}（原{max_tokens}）")

            try:
                logger.info(
                    f"调用模型：{model_name}，版本：{model_version or config['default_model_version']}，"
                    f"temperature={temperature}，max_tokens={final_max_tokens}"
                )
                
                # 根据模型名称调用对应的函数
                if model_name == "ernie":
                    result = self._call_ernie(
                        api_key=config["api_key"],
                        api_url=config["api_url"],
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=final_max_tokens,  # 使用调整后的参数
                        timeout=config["timeout"],
                        model_version=model_version or config["default_model_version"]
                    )
                elif model_name == "qianwen":
                    result = self._call_qianwen(
                        api_key=config["api_key"],
                        api_url=config["api_url"],
                        prompt=prompt,
                        temperature=temperature,
                        max_tokens=final_max_tokens,  # 使用调整后的参数
                        timeout=config["timeout"],
                        model_version=model_version or config["default_model_version"]
                    )
                else:
                    continue

                # 记录耗时
                elapsed = round(time.time() - start_time, 2)
                logger.info(f"模型 {model_name} 调用完成，耗时{elapsed}秒，状态：{result['status']}")
                logger.info(f"【真实调用AI】使用API Key前8位：{config['api_key'][:8]}，请求地址：{config['api_url']}")

                # 如果调用成功，立即返回结果
                if result["status"] == "success":
                    return {
                        "status": "success",
                        "content": result["content"],
                        "model_used": model_name
                    }
                else:
                    logger.warning(f"模型 {model_name} 调用失败：{result['content']}")

            except Exception as e:
                elapsed = round(time.time() - start_time, 2)
                logger.error(
                    f"调用模型 {model_name} 时发生异常（耗时{elapsed}秒）：{str(e)}",
                    exc_info=True  # 记录完整堆栈信息
                )
                continue

        # 如果所有目标模型都失败了
        return {
            "status": "failure",
            "content": f"【调用失败】目标模型{target_models}均调用失败，请检查网络或稍后重试",
            "model_used": None
        }

    # ========== 新增：ai_review_service方法（适配cad_service的调用） ==========
    def ai_review_service(self, ocr_structured_data: list, filename: str) -> Dict[str, Any]:
        """
        电气图纸AI审查核心方法（适配cad_service的调用参数）
        :param ocr_structured_data: OCR识别的结构化数据列表
        :param filename: 文件名
        :return: 符合cad_service预期的返回格式
        """
        # 构建电气图纸审查的提示词（精简长度，避免token超限）
        # 构建电气图纸审查的提示词（动态拼接5条规则）
        rule_prompts = {
            "wire_color": ELECTRIC_REVIEW_RULES["wire_color"]["prompt"],
            "symbol_standard": ELECTRIC_REVIEW_RULES["symbol_standard"]["prompt"],
            "safety_distance": ELECTRIC_REVIEW_RULES["safety_distance"]["prompt"],
            "load_balance": ELECTRIC_REVIEW_RULES["load_balance"]["prompt"],
            "grounding_spec": ELECTRIC_REVIEW_RULES["grounding_spec"]["prompt"]
        }
        # 生成带5条规则的完整提示词
        final_prompt = GENERAL_REVIEW_PROMPT.format(**rule_prompts) + f"""
        \n\n需审查的图纸相关信息：
        文件名：{filename}
        OCR结构化数据：{ocr_structured_data[:2000]}
        """
        
        # 调用AI模型（max_tokens降到2048，适配文心一言）
        ai_result = self.call_ai(
            prompt=final_prompt,  # 这里用新的final_prompt
            model_name=None,
            temperature=0.2,
            max_tokens=2048
        )
        
        # 转换为cad_service预期的返回格式
        if ai_result["status"] == "success":
            return {
                "status": "success",
                "review_result": ai_result["content"],
                "model_used": ai_result["model_used"],
                "filename": filename
            }
        else:
            return {
                "status": "failed",
                "error": ai_result["content"],
                "message": "AI审查失败",
                "filename": filename
            }

    def _call_ernie(
        self, 
        api_key: str, 
        api_url: str, 
        prompt: str, 
        temperature: float, 
        max_tokens: int, 
        timeout: int,
        model_version: str
    ) -> Dict[str, Any]:
        """调用百度文心一言API"""
        request_data = {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": model_version  # 使用指定版本
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=request_data,
                timeout=timeout
            )
            response.raise_for_status()  # 触发HTTP错误（如4xx/5xx）
            resp_json = response.json()

            # 日志记录响应概要（避免敏感信息）
            logger.debug(f"文心一言响应：{str(resp_json)[:500]}")

            if isinstance(resp_json, dict):
                if "choices" in resp_json and len(resp_json["choices"]) > 0:
                    return {"status": "success", "content": resp_json["choices"][0]["message"]["content"]}
                else:
                    err_msg = f"【返回格式异常】无'result'字段，响应：{str(resp_json)[:500]}"
                    return {"status": "failure", "content": err_msg}
            else:
                err_msg = f"【返回非字典格式】响应：{str(resp_json)[:500]}"
                return {"status": "failure", "content": err_msg}

        except requests.exceptions.HTTPError as e:
            err_msg = f"【HTTP错误】状态码：{e.response.status_code}，响应：{e.response.text[:500]}"
            return {"status": "failure", "content": err_msg}
        except requests.exceptions.Timeout:
            err_msg = "【超时错误】请求超过60秒未响应"
            return {"status": "failure", "content": err_msg}
        except Exception as e:
            err_msg = f"【调用异常】{str(e)}"
            return {"status": "failure", "content": err_msg}

    def _call_qianwen(
        self, 
        api_key: str, 
        api_url: str, 
        prompt: str, 
        temperature: float, 
        max_tokens: int, 
        timeout: int,
        model_version: str
    ) -> Dict[str, Any]:
        """调用阿里云通义千问API"""
        request_data = {
            "model": model_version,  # 使用指定版本
            "input": {
                "messages": [{"role": "user", "content": prompt}]
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens
            }
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=request_data,
                timeout=timeout
            )
            response.raise_for_status()
            resp_json = response.json()

            # 日志记录响应概要
            logger.debug(f"通义千问响应：{str(resp_json)[:500]}")

            if isinstance(resp_json, dict):
                if "output" in resp_json and "text" in resp_json["output"]:
                    return {"status": "success", "content": resp_json["output"]["text"]}
                else:
                    err_msg = f"【返回格式异常】无'output.text'字段，响应：{str(resp_json)[:500]}"
                    return {"status": "failure", "content": err_msg}
            else:
                err_msg = f"【返回非字典格式】响应：{str(resp_json)[:500]}"
                return {"status": "failure", "content": err_msg}

        except requests.exceptions.HTTPError as e:
            err_msg = f"【HTTP错误】状态码：{e.response.status_code}，响应：{e.response.text[:500]}"
            return {"status": "failure", "content": err_msg}
        except requests.exceptions.Timeout:
            err_msg = "【超时错误】请求超过60秒未响应"
            return {"status": "failure", "content": err_msg}
        except Exception as e:
            err_msg = f"【调用异常】{str(e)}"
            return {"status": "failure", "content": err_msg}

# ========== 保留实例化（供cad_service导入） ==========
ai_service = AIService()
ai_review_service = ai_service  # 直接指向同一个实例，避免重复初始化