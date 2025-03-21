import hashlib

def generate_password_hash(password: str, username: str) -> str:
    # 第一次 md5
    first_hash = hashlib.md5(password.encode()).hexdigest()
    
    # 拼接 username
    combined = first_hash + username
    
    # 第二次 md5
    final_hash = hashlib.md5(combined.encode()).hexdigest()
    
    return final_hash

# 使用示例
password = "123456"
username = "w888"
hash_result = generate_password_hash(password, username)
print(hash_result)