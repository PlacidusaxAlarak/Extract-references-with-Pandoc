# file_writer.py
# 该文件定义了一个辅助函数，用于将内容安全地写入文件。

from pathlib import Path  # 从pathlib库导入Path类，用于以面向对象的方式操作文件系统路径。


def save_html_report(content: str, file_path: str) -> None:
    """
    将字符串内容安全地保存到指定的 HTML 文件中。

    这个函数会首先确保目标文件所在的父目录存在，如果不存在，它会自动创建。
    然后，它使用 UTF-8 编码将内容写入文件。

    Args:
        content (str): 要保存的 HTML 字符串内容。
        file_path (str): 目标 HTML 文件的完整路径。

    Raises:
        IOError: 如果在文件写入过程中发生 I/O（输入/输出）相关的错误。
    """
    try:
        # 将传入的文件路径字符串转换为一个Path对象，以便使用其面向对象的方法。
        path = Path(file_path)
        
        # 获取该文件路径的父目录（例如，对于'/a/b/c.txt'，父目录是'/a/b'）。
        # 然后调用.mkdir()方法来创建这个目录。
        # `parents=True`参数确保如果路径中的多层父目录（如'/a'和'/a/b'）都不存在，它们会被一并创建。
        # `exist_ok=True`参数表示如果目标目录已经存在，则不会引发错误，使操作具有幂等性。
        path.parent.mkdir(parents=True, exist_ok=True)

        # 使用`with open(...)`语句打开文件以进行写入。这能确保文件在操作完成后被自动关闭。
        # 'w'模式表示写入模式。如果文件已存在，其内容将被清空；如果文件不存在，则会创建新文件。
        # `encoding='utf-8'`指定使用UTF-8编码写入文件，这是Web和现代文本文件的标准编码。
        with open(path, 'w', encoding='utf-8') as f:
            # 调用文件对象的.write()方法，将传入的`content`字符串写入到文件中。
            f.write(content)
        
        # 在成功写入文件后，向控制台打印一条确认消息，告知用户报告已保存的位置。
        print(f"报告已成功保存至: {file_path}")
        
    # 捕获在文件操作过程中可能发生的IOError（例如，由于权限不足或磁盘已满）。
    except IOError as e:
        # 如果发生错误，向控制台打印一条详细的错误消息，包括文件名和具体的异常信息。
        print(f"保存文件到 '{file_path}' 时出错: {e}")
        # 重新抛出异常，以便上层调用代码可以捕获并处理这个失败情况。
        raise
