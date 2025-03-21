import re


def get_code_from_md_code_block(content: str) -> str:
    """
    Extract code from markdown code block.
    """
    #删除带有```的行
    all_lines = content.split("\n")
    code_lines = []
    for line in all_lines:
        if line.count("```")>0:
            continue
        code_lines.append(line)
    return "\n".join(code_lines)
if __name__ == '__main__':
    test_content = """```javascript
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import App from "../App";

test("displays loading indicator when requestSent is true and emailResponse is empty", () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText(/email address/i), {
    target: { value: "test@example.com" },
  });
  fireEvent.click(screen.getByText(/send/i));
  expect(screen.getByText(/loading.../i)).toBeInTheDocument();
});

test("displays email response when requestSent is false and emailResponse is not empty", () => {
  render(<App />);
  fireEvent.change(screen.getByLabelText(/email address/i), {
    target: { value: "test@example.com" },
  });
  fireEvent.click(screen.getByText(/send/i));
  fireEvent.click(screen.getByText(/send/i));
  expect(screen.getByText(/email response/)).toBeInTheDocument();
});
```
"""
    print(get_code_from_md_code_block(test_content))  # def test_function():\n    print("Hello, world!")


def get_test_status_from_stdout(stdout):
    if not stdout:
        return None
        
    # 格式1: "Tests: X failed, Y total"
    pattern1 = r'Tests:\s*(\d+)\s*failed,\s*(\d+)\s*total'
    match = re.search(pattern1, stdout)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    
    # 格式2: "X failed, Y passed, Z total"
    pattern2 = r'(\d+)\s*failed,\s*(\d+)\s*passed,\s*(\d+)\s*total'
    match = re.search(pattern2, stdout)
    if match:
        return (int(match.group(1)), int(match.group(3)))

    # 格式3: "Tests run: X, Failures: Y, Errors: Z, Skipped: W"
    pattern3 = r'Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+)'
    match = re.search(pattern3, stdout)
    if match:
        failed = int(match.group(2)) + int(match.group(3))  # 失败数 = Failures + Errors
        total = int(match.group(1))
        return (failed, total)
    
    # 格式4: "X examples, Y failures"
    pattern4 = r'(\d+)\s*examples?,\s*(\d+)\s*failures?'
    match = re.search(pattern4, stdout)
    if match:
        total = int(match.group(1))
        failed = int(match.group(2))
        return (failed, total)
        
    return None

if __name__ == '__main__':
    test_stdout = "Tests run: 2, Failures: 0, Errors: 0, Skipped: 0"
    print(get_test_status_from_stdout(test_stdout))  # (2, 2)