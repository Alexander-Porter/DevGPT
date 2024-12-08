import json
import re
import pandas as pd
import requests
import threading
import time
from urllib.parse import urlparse
from sklearn.metrics import jaccard_score
from queue import Queue

# Define utility functions for extracting identifiers and calculating similarity

def extract_identifiers(code):
    pattern = r'\b[_a-zA-Z][_a-zA-Z0-9]*\b'
    return re.findall(pattern, code)

def extract_function_names(code):
    pattern = r'\b([_a-zA-Z][_a-zA-Z0-9]*)\s*\('
    return re.findall(pattern, code)

def normalize_identifier(identifier):
    return re.sub(r'\W+', '', identifier).lower()

def remove_test_prefix(identifier):
    return re.sub(r'\btest\b', '', identifier, flags=re.IGNORECASE)

def calculate_normalized_jaccard_similarity(set1, set2):
    normalized_set1 = {normalize_identifier(identifier) for identifier in set1}
    normalized_set2 = {normalize_identifier(identifier) for identifier in set2}
    return len(normalized_set1.intersection(normalized_set2)) / len(normalized_set1.union(normalized_set2)) if len(normalized_set1.union(normalized_set2)) > 0 else 0

def adjust_similarity_score_for_function_match(src_functions, test_functions, original_score, boost_factor=1.5):
    normalized_src_functions = {normalize_identifier(func) for func in src_functions}
    normalized_test_functions = {normalize_identifier(func) for func in test_functions}
    if normalized_src_functions.intersection(normalized_test_functions):
        return original_score * boost_factor
    return original_score

def evaluate_code_complexity(code):
    """
    Evaluate the complexity of the code.
    Criteria include:
    - Number of functions/classes defined
    - Length of the code
    - Number of control flow structures (if, for, while)
    - Number of nested blocks (loops or conditionals)
    - Number of unique identifiers (functions, variables)
    
    The score is cumulative based on these factors.
    """
    function_pattern = r'\bfunction\b|\bdef\b|\bclass\b'
    control_flow_pattern = r'\bif\b|\belse\b|\bfor\b|\bwhile\b|\bswitch\b|\bcase\b'
    nested_structure_pattern = r'[{}]|[\n\t]*\bif\b|\bfor\b|\bwhile\b'
    
    function_count = len(re.findall(function_pattern, code))
    control_flow_count = len(re.findall(control_flow_pattern, code))
    nested_structure_count = len(re.findall(nested_structure_pattern, code))
    unique_identifiers = set(extract_identifiers(code))
    unique_identifier_count = len(unique_identifiers)
    code_length = len(code.splitlines())
    
    score = (
        function_count * 2 +
        control_flow_count * 1.5 +
        nested_structure_count * 1.2 +
        unique_identifier_count * 0.5 +
        code_length * 0.1
    )
    
    return score

def evaluate_prompt_clarity(prompt):
    """
    Evaluate the clarity of the prompt based on the number of verbs that are common in code generation prompts.
    These verbs often describe actions to be taken and provide clarity to the prompt.
    """
    verb_pattern = r'\b(?:create|generate|convert|build|fetch|give|update|delete|write|read|set|get|initialize|define|implement|calculate|process|render|test|assert|check|validate|return|loop|repeat|print|display|load|save|deploy)\b'
    verbs = re.findall(verb_pattern, prompt, flags=re.IGNORECASE)
    return len(verbs)

def get_github_stars(url, queue, rate_limit):
    """
    Get the number of stars for a given GitHub repository.
    Use a queue to store the result and ensure rate limit is released.
    """
    try:
        parsed_url = urlparse(url)
        if parsed_url.netloc == 'github.com':
            path_parts = parsed_url.path.strip('/').split('/')
            if len(path_parts) >= 2:
                repo_owner = path_parts[0]
                repo_name = path_parts[1]
                api_url = f'https://api.github.com/repos/{repo_owner}/{repo_name}'
                response = requests.get(api_url, timeout=10)
                if response.status_code == 200:
                    repo_info = response.json()
                    print(f"GitHub Stars for {repo_owner}/{repo_name}: {repo_info.get('stargazers_count', 0)}")
                    queue.put(repo_info.get('stargazers_count', 0))
                    return
        queue.put(0)
    except requests.RequestException as e:
        queue.put(0)
    finally:
        rate_limit.release()

# Main function to process JSON files and rank based on benchmark suitability
def process_json_files(file_paths):
    all_results = []
    threads = []
    rate_limit = threading.Semaphore(5)  # Limit to 5 concurrent GitHub API requests
    
    for file_path in file_paths:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            for item in data:
                if "most_possible_src_code" in item and "Code" in item:
                    # Extract identifiers and function names
                    src_code = item["most_possible_src_code"]
                    test_code = item["Code"]
                    src_identifiers = set(extract_identifiers(src_code))
                    test_identifiers = set(extract_identifiers(test_code))
                    src_functions = set(extract_function_names(src_code))
                    test_functions = set(extract_function_names(test_code))
                    
                    # Combine identifiers and calculate similarity
                    src_combined = src_identifiers.union(src_functions)
                    test_combined = test_identifiers.union(test_functions)
                    
                    # Calculate normalized Jaccard similarity
                    similarity_score = calculate_normalized_jaccard_similarity(src_combined, test_combined)
                    
                    # Adjust similarity score for function name matches
                    final_similarity_score = adjust_similarity_score_for_function_match(src_functions, test_functions, similarity_score)
                    
                    # Calculate code complexity score
                    code_complexity_score = evaluate_code_complexity(src_code)
                    
                    # Calculate prompt clarity score
                    prompt_clarity_score = evaluate_prompt_clarity(item.get("LastUerPrompt", ""))
                    
                    # Calculate combined benchmark suitability score
                    benchmark_suitability_score = (final_similarity_score * 0.4) + (code_complexity_score * 0.3) + (prompt_clarity_score * 0.3)
                    
                    # Check for GitHub stars if the source is a GitHub link
                    github_stars = 0
                    if "Source" in item and "github.com" in item["Source"]:
                        rate_limit.acquire()
                        queue = Queue()
                        thread = threading.Thread(target=get_github_stars, args=(item["Source"], queue, rate_limit))
                        thread.start()
                        threads.append((thread, queue))
                    
                    # Update original item with new scores
                    item["Benchmark_Suitability_Score"] = benchmark_suitability_score
                    item["Matches_Function_Adjusted"] = final_similarity_score >= 0.1
                    item["Code_Complexity_Score"] = code_complexity_score
                    item["Prompt_Clarity_Score"] = prompt_clarity_score
                    item["GitHub_Stars"] = github_stars
                
                # Append updated item to results
                all_results.append(item)
    
    # Wait for all threads to complete and collect GitHub stars
    for thread, queue in threads:
        thread.join()
        github_stars = queue.get()
        for item in all_results:
            if "Source" in item and "github.com" in item["Source"] and item["GitHub_Stars"] == 0:
                item["GitHub_Stars"] = github_stars
                break
    
    # Sort results by Benchmark_Suitability_Score
    all_results = sorted(all_results, key=lambda x: x.get("Benchmark_Suitability_Score", 0), reverse=True)
    
    # Save updated data to a new JSON file
    with open('updated_benchmark_results.json', 'w', encoding='utf-8') as outfile:
        json.dump(all_results, outfile, indent=4, ensure_ascii=False)
    
    print("Results have been saved to 'updated_benchmark_results.json'")

# Example usage
if __name__ == "__main__":
    file_paths = ["cleaned_data.json"]
    process_json_files(file_paths)
