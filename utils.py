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


def get_test_status_from_stdout(stdout: str) -> str:
    """
    Get test status from stdout.
    """
    #looks like "Tests:       2 failed, 2 total" use regex to extract the number of failed and total tests
    #or 1 failed, 3 passed, 4 total
    import re
    pattern = re.compile(r"Tests:\s+(\d+)\s+failed,\s+(\d+)\s+total")
    match = pattern.search(stdout)
    if match:
        failed = int(match.group(1))
        total = int(match.group(2))
        return (failed, total)
    pattern2 = re.compile(r"(\d+)\s+failed,\s+(\d+)\s+passed,\s+(\d+)\s+total")
    match2 = pattern2.search(stdout)
    if match2:
        failed = int(match2.group(1))
        total = int(match2.group(3))
        return (failed, total)
    pattern3 = re.compile(r"(\d+)\s+passed,\s+(\d+)\s+total")
    match3 = pattern3.search(stdout)
    if match3:
        failed = 0
        total = int(match3.group(2))
        return (failed, total)

if __name__ == '__main__':
    test_stdout = "Tests:       2 failed, 2 total"
    print(get_test_status_from_stdout(test_stdout))  # (2, 2)