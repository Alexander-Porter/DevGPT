import os
import shutil
import tempfile
import traceback
import docker

from token_count import TokenCounter
from OAI import FlowControlOpenAIClient
from utils import get_code_from_md_code_block, get_test_status_from_stdout
class Task:
    def __init__(self, project_path, base_url, api_key, model="gpt-4", tpm_limit=90000, rpm_limit=300):
        self.project_path = project_path
        self.temp_path = tempfile.mkdtemp()
        self.docker_client = docker.from_env()
        self.model=model
        self.client=FlowControlOpenAIClient(model=model, tpm_limit=tpm_limit, rpm_limit=rpm_limit, base_url=base_url, api_key=api_key)
        self.test_files_path = None
        self.results = []
    def copy_project_to_temp(self):
        try:
            shutil.copytree(self.project_path, self.temp_path, dirs_exist_ok=True)
        except Exception as e:
            print(f"Failed to copy project to temp directory: {e}")
            raise

    def clear_test_files(self):
        for root, _, files in os.walk(self.temp_path):
            for file in files:
                if ('test' in file.lower()) or ('spec' in file.lower()):
                    test_file_path = os.path.join(root, file)
                    try:
                        open(test_file_path, 'w').close()  # Empty the content of the test file
                        self.test_files_path = test_file_path
                    except Exception as e:
                        print(f"Failed to clear test file {file}: {e}")
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
                tree_structure += f'{sub_indent}{f}\n'
                try:
                    with open(os.path.join(root, f), 'r') as file:
                        content = file.read()
                        if content=="":
                            content="<UNDONE>"
                        tree_structure += f'{sub_indent}    Content: {content}\n'
                except:
                    tree_structure += f'{sub_indent}    Content: <Unable to read>\n'
        return tree_structure

    def call_ai_to_complete_tests(self):

        directory_tree = self.get_directory_tree()
        print("Directory Tree:", directory_tree)
        try:
            response = self.client.call_openai_api(
                model=self.model,
                messages=[
                    {"role": "system", "content": "The following is the directory structure of a project with a missing unit test. Please complete a centain unit test file based on the content user provided. Only return pure code, no comments or explanations are needed. **DO NOT** use markdown code blocks(``` ```)."},
                    {"role": "user", "content": f"'''{directory_tree}''' \n the unit tests files {self.test_files_path} need to be completed."}
                ],
                stream=False
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Failed to call AI API to complete tests: {e}")
            raise

    def write_completed_tests(self, ai_generated_tests):
        cleaned = get_code_from_md_code_block(ai_generated_tests)
        print("AI Generated Tests:", cleaned)
        # Write the AI-generated code back to the test files
        # (Assuming it contains instructions to write to specific files)
        # This part can be made more sophisticated depending on AI's response structure
        test_files = [os.path.join(root, file) for root, _, files in os.walk(self.temp_path) for file in files if ('test' in file.lower()) or ('spec' in file.lower())]
        if len(test_files) == 0:
            raise Exception("No test files found to update.")
        try:
            with open(test_files[0], 'w') as test_file:
                test_file.write(cleaned)
        except Exception as e:
            print(f"Failed to write completed tests to file: {e}")
            raise

    def docker_run_and_get_output(self):
        try:
            container = self.docker_client.containers.run(
                image=self.build_docker_image(),
                detach=True,
                auto_remove=False  # 改为False以便查看日志
            )
            
            # 等待容器结束
            container.wait()
            
            # 获取所有日志
            output = container.logs(stdout=True, stderr=True).decode('utf-8')
            print("Container output:", output)  # 添加日志打印
            
            # 清理容器
            container.remove()
            
            return output
        except docker.errors.DockerException as e:
            print(f"Docker run failed: {e}")
            raise

    def build_docker_image(self):
        try:
            print("\n=== 开始构建 Docker 镜像 ===")
            print(f"构建路径: {self.temp_path}")
            
            # 检查 Dockerfile 是否存在
            dockerfile_path = os.path.join(self.temp_path, 'Dockerfile')
            if not os.path.exists(dockerfile_path):
                raise FileNotFoundError(f"Dockerfile not found at {dockerfile_path}")
                
            # 打印 Dockerfile 内容
            print("\n=== Dockerfile 内容 ===")
            with open(dockerfile_path, 'r') as f:
                print(f.read())
                
            print("\n=== 开始构建过程 ===")
            image, build_logs = self.docker_client.images.build(
                path=self.temp_path,
                rm=True,
                tag="test_pipeline_image",
                forcerm=True,  # 强制删除中间容器
                nocache=True   # 不使用缓存
            )
            
            print("\n=== 构建日志 ===")
            for log in build_logs:
                if 'stream' in log:
                    print(log['stream'].strip())
                    if get_test_status_from_stdout(log.get('stream')):
                        self.results.append(get_test_status_from_stdout(log.get('stream')))
                elif 'error' in log:
                    print(f"错误: {log['error']}")
                elif 'status' in log:
                    print(f"状态: {log['status']}")
                else:
                    print(f"其他日志: {log}")
                    
            print(f"\n=== 镜像构建成功 ===")
            print(f"镜像标签: {image.tags[0]}")
            print(f"镜像ID: {image.id}")
            
            return image.tags[0]
            
        except docker.errors.BuildError as e:
            print(f"\n=== 构建失败 ===")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print("\n详细错误日志:")
            if hasattr(e, 'build_log'):
                for log in e.build_log:
                    print(log)
                    if 'stream' in log:
                        print(log['stream'].strip())

                        if get_test_status_from_stdout(log.get('stream')):
                            self.results.append(get_test_status_from_stdout(log.get('stream')))

            
        except Exception as e:
            print(f"\n=== 意外错误 ===")
            print(f"错误类型: {type(e).__name__}")
            print(f"错误信息: {str(e)}")
            print(f"堆栈跟踪:\n{traceback.format_exc()}")
            raise

    def run(self):
        # Step 1: Copy the folder to temp location
        self.copy_project_to_temp()

        # Step 2: Clear the test files
        self.clear_test_files()

        # Step 3: Get directory tree and call AI to complete tests
        ai_generated_tests = self.call_ai_to_complete_tests()

        # Step 4: Write the generated tests
        self.write_completed_tests(ai_generated_tests)

        # Step 5: Docker build and run
        try:
            docker_output = self.docker_run_and_get_output()
        except Exception as e:
            print(f"Failed to run Docker: {e}")
            return 1
        print("Docker Output:", docker_output)
        return 0



with open(".env", "r") as f:
    for line in f:
        key, value = line.strip().split("=")
        os.environ[key] = value
# Example usage
if __name__ == "__main__":

    base_url = "https://api.siliconflow.cn/v1"
    api_key = os.getenv("API_KEY")
    task = Task(project_path="./java_playground/gennemsnit_calculator", base_url=base_url, api_key=api_key,model="Qwen/Qwen2.5-Coder-7B-Instruct", tpm_limit=90000, rpm_limit=300)
    all_runs = []
    for i in range(3):
        task.run()
        all_runs.append(task.results)
    with open("all_runs.txt", "w") as f:
        f.write("Qwen/Qwen2.5-Coder-7B-Instruct\n")
        f.write(str(all_runs))