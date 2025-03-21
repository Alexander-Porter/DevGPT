import os
import shutil
import subprocess
import sys
import tempfile
import datetime
import logging
import re
import threading

from OAI import FlowControlOpenAIClient
from utils import get_code_from_md_code_block, get_test_status_from_stdout

# 清理 ANSI 转义字符
def _clean_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

# 配置日志
def setup_logger(project_name):
    """为每个项目创建独立的 logger 实例"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = f"logs/{project_name}_{timestamp}.log"

    # 确保日志目录存在
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # 创建 logger 实例（不共享）
    logger = logging.getLogger(project_name)  # 以项目名称命名，保证唯一
    logger.setLevel(logging.INFO)  # 设置日志级别

    # 防止重复添加 handler
    if not logger.handlers:
        # 创建文件 handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))

        # 创建控制台 handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(message)s'))

        # 绑定 handler
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


class Task:
    def __init__(self, project_path, base_url, api_key, model="gpt-4", tpm_limit=90000, rpm_limit=300, project_name="default"):
        self.project_path = project_path
        self.temp_path = tempfile.mkdtemp()
        self.model = model
        self.client = FlowControlOpenAIClient(model=model, tpm_limit=tpm_limit, rpm_limit=rpm_limit,
                                               base_url=base_url, api_key=api_key)
        self.test_files_path = None
        self.results = []
        self.output_lines = []
        self.logger = setup_logger(project_name)  # 每个任务创建独立的 logger

    def copy_project_to_temp(self):
        try:
            shutil.copytree(self.project_path, self.temp_path, dirs_exist_ok=True)
        except Exception as e:
            self.logger.error(f"Failed to copy project to temp directory: {e}")
            raise

    def clear_test_files(self):
        for root, _, files in os.walk(self.temp_path):
            for file in files:
                if ('test' in file.lower()) or ('spec' in file.lower()):
                    test_file_path = os.path.join(root, file)
                    try:
                        open(test_file_path, 'w').close()  # 清空测试文件内容
                        self.test_files_path = test_file_path
                    except Exception as e:
                        self.logger.error(f"Failed to clear test file {file}: {e}")
                        raise

    def get_directory_tree(self, directory=None):
        if directory is None:
            directory = self.temp_path
        tree_structure = ""
        for root, dirs, files in os.walk(directory):
            level = root.replace(directory, '').count(os.sep)
            indent = ' ' * 4 * level
            tree_structure += f'{indent}{os.path.basename(root)}/\n'
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                full_path = os.path.join(root, f)
                try:
                    with open(full_path, 'r') as file_obj:
                        content = file_obj.read()
                        if content == "":
                            content = "<UNDONE>"
                        tree_structure += f'{sub_indent}    Content: {content}\n'
                except Exception:
                    tree_structure += f'{sub_indent}    Content: <Unable to read>\n'
        return tree_structure

    def call_ai_to_complete_tests(self):
        directory_tree = self.get_directory_tree()
        self.logger.info("Directory Tree:\n" + directory_tree)
        try:
            response = self.client.call_openai_api(
                model=self.model,
                messages=[{
                    "role": "system", 
                    "content": "The following is the directory structure of a project with a missing unit test. Please complete a certain unit test file based on the content user provided. **Only** use dependencies declared in package/requirement file already. Only return pure code, no comments or explanations are needed. **DO NOT** use markdown code blocks(``` ```)."
                },
                {
                    "role": "user", 
                    "content": f"'''{directory_tree}''' \n the unit tests files {self.test_files_path} need to be completed."
                }], stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"Failed to call AI API to complete tests: {e}")
            raise

    def write_completed_tests(self, ai_generated_tests):
        cleaned = get_code_from_md_code_block(ai_generated_tests)
        self.logger.info("AI Generated Tests:\n" + cleaned)
        test_files = [os.path.join(root, file) for root, _, files in os.walk(self.temp_path)
                      for file in files if ('test' in file.lower()) or ('spec' in file.lower())]
        if not test_files:
            raise Exception("No test files found to update.")
        try:
            with open(test_files[0], 'w') as test_file:
                test_file.write(cleaned)
        except Exception as e:
            self.logger.error(f"Failed to write completed tests to file: {e}")
            raise

    def build_docker_image(self):
        try:
            self.logger.info("\n=== 开始构建 Docker 镜像 ===")
            self.logger.info(f"构建路径: {self.temp_path}")
            dockerfile_path = os.path.join(self.temp_path, 'Dockerfile')
            if not os.path.exists(dockerfile_path):
                raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")
            with open(dockerfile_path, 'r',encoding='utf-8') as f:
                dockerfile_content = f.read()
            self.logger.info("\n=== Dockerfile 内容 ===\n" + dockerfile_content)
            self.logger.info("\n=== 开始构建过程 ===")
            command = ["docker", "build", "-t", "test_pipeline_image", self.temp_path]
            self.logger.info("执行命令: " + " ".join(command))
            process = subprocess.Popen(command,encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if "error" in line.lower():
                        self.logger.error(f"[{timestamp}] {line}")
                    else:
                        self.logger.info(f"[{timestamp}] {line}")
            process.wait()
            if process.returncode != 0:
                self.logger.error(f"Docker build 失败，退出码：{process.returncode}")
                raise Exception("Docker build failed")
            self.logger.info("=== 镜像构建成功 ===")
            return "test_pipeline_image"
        except Exception as e:
            self.logger.error("构建 Docker 镜像过程中出现异常: " + str(e))
            raise

    def docker_run_and_get_output(self):
        try:
            image_tag = self.build_docker_image()
            self.logger.info("\n=== 开始运行 Docker 容器 ===")
            command = ["docker", "run", image_tag]
            self.logger.info("执行命令: " + " ".join(command))
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.logger.info(f"[{timestamp}] {line}")
                    self.output_lines.append(line)
            process.wait()
            exit_code = process.returncode
            self.logger.info(f"容器退出，退出码：{exit_code}")
            return "\n".join(self.output_lines)
        except Exception as e:
            self.logger.error("运行 Docker 容器过程中出现异常: " + str(e))
            raise

    def run(self):
        self.copy_project_to_temp()
        self.clear_test_files()
        ai_generated_tests = self.call_ai_to_complete_tests()
        self.write_completed_tests(ai_generated_tests)

        try:
            docker_output = self.docker_run_and_get_output()
            results = []
            for line in docker_output.split('\n'):
                result = get_test_status_from_stdout(line)
                if result is not None:
                    results.append(result)

            if results:
                self.results = results[-1]  
                self.logger.info(f"Final test result: {self.results}")
            else:
                self.results = (-1, -1)
        except Exception as e:
            self.results = (-1, -1)
            self.logger.error(f"Failed to run Docker: {e}")
            return 1
        
        self.logger.info("Docker Output:\n" + docker_output)
        return 0


def run_task(project_name, base_url, api_key, model_name, results):
    task = Task(project_path=f"./java_playground/{project_name}",
                base_url=base_url, api_key=api_key,
                model=model_name, tpm_limit=90000, rpm_limit=300, project_name=project_name)
    all_runs = []
    for _ in range(5):
        task.run()
        all_runs.append(task.results)
    results[project_name] = all_runs


if __name__ == "__main__":
    # 从 .env 文件读取环境变量
    with open(".env", "r") as f:
        for line in f:
            key, value = line.strip().split("=")
            os.environ[key] = value
    
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key = os.getenv("API_KEY")
    model_name = "llama3.3-70b-instruct"
    
    # 允许用户选择多个文件夹
    project_names  = [
    "rails_filter_project",
    "basho_corrected",
    "extract_Content",
    "gennemsnit_calculator", 
    "react_app_fixed_jsdom",
    "roman_conversion",
    "text_formatter_final"
]
    #project_names = ["rails_filter_project", "extract_Content"]
    threads = []
    results = {}
    
    for project_name in project_names:
        thread = threading.Thread(target=run_task, args=(project_name, base_url, api_key, model_name, results))
        threads.append(thread)
        thread.start()
    
    for thread in threads:
        thread.join()
    
    # 输出所有结果
    output_file = f"{model_name.replace('/', '_')}_results.txt"
    with open(output_file, "w") as f:
        f.write(f"{model_name}\n")
        f.write(str(results))
