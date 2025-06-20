import os
import re


def read_and_format_api_keys(directory):
    """
    读取指定目录下的所有文件，提取API密钥，并对源文件进行格式化，确保每个key占一行。
    """
    all_api_keys = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            with open(filepath, "r+", encoding="utf-8") as f:
                content = f.read()
                # 使用正则表达式按空格、逗号等分隔符分割
                keys = re.split(r"[\s,]+", content)
                # 过滤掉空的字符串
                cleaned_keys = [key for key in keys if key]

                if cleaned_keys:
                    all_api_keys.extend(cleaned_keys)

                    # 格式化内容，每个key占一行
                    formatted_content = "\n".join(cleaned_keys)

                    # 只有当内容改变时才写回文件
                    if formatted_content != content:
                        f.seek(0)
                        f.write(formatted_content)
                        f.truncate()

    return all_api_keys


def main():
    """
    主函数，用于读取API密钥并打印。
    """
    keys_directory = "keys/"
    api_keys = read_and_format_api_keys(keys_directory)
    print("格式化并读取的API密钥列表:")
    for key in api_keys:
        print(key)


if __name__ == "__main__":
    main()
