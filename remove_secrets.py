import re

def clean_line(line):
    # 删除包含 ghp_ 或邮箱等敏感信息的行
    if re.search(r"ghp_|2068246879@qq\.com", line):
        return ""
    return line

def clean_file(path, lines):
    return [clean_line(line) for line in lines]

