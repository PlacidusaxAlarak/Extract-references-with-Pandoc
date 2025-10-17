# archive_handler.py
# 这个模块提供了用于处理（主要是解压）不同格式归档文件的功能。

# --- 导入标准库 ---
import zipfile  # 导入zipfile库，用于处理.zip格式的压缩文件。
import tarfile  # 导入tarfile库，用于处理.tar、.tar.gz、.tar.bz2等tar归档文件。
import gzip     # 导入gzip库，用于处理.gz格式的单个压缩文件。
import shutil   # 导入shutil库，它提供了高级的文件操作功能，如此处的copyfileobj用于流式复制文件内容。
from pathlib import Path  # 从pathlib库导入Path类，用于以面向对象的方式操作文件系统路径。
from typing import List   # 从typing库导入List，用于提供类型提示，增强代码可读性。

# --- 函数定义 ---

def extract_archive(archive_path: str, extract_to_dir: str) -> Path:
    """
    解压指定的归档文件到目标目录。
    此函数能够处理多种常见的归档格式，并对.gz文件有特别的健壮性处理。

    支持的格式: .zip, .tar, .gz, .tar.gz, .tgz, .tar.bz2, .tbz2

    Args:
        archive_path (str): 归档文件的完整路径。
        extract_to_dir (str): 文件将被解压到的目标目录路径。

    Returns:
        Path: 一个 `pathlib.Path` 对象，指向解压后文件所在的目录。

    Raises:
        FileNotFoundError: 如果指定的归档文件不存在。
        ValueError: 如果归档文件的格式不被支持。
    """
    # 将传入的字符串路径转换为Path对象，这使得路径操作更加安全和方便。
    archive_file = Path(archive_path)
    # 同样，将目标目录的字符串路径也转换为Path对象。
    extract_path = Path(extract_to_dir)

    # 使用Path对象的.exists()方法检查归档文件是否存在于文件系统中。
    if not archive_file.exists():
        # 如果文件不存在，则构造一个FileNotFoundError并抛出，终止函数执行。
        raise FileNotFoundError(f"错误: 归档文件未找到: {archive_path}")

    # 打印一条信息到控制台，告知用户正在开始解压过程。
    print(f"--- 正在解压 '{archive_file.name}' 到 '{extract_path}'...")
    
    # 使用Path对象的.mkdir()方法来创建目标目录。
    # `parents=True`参数意味着如果路径中的父目录不存在，也会一并创建（类似于 `mkdir -p`）。
    # `exist_ok=True`参数表示如果目录已经存在，则不会抛出错误。
    extract_path.mkdir(parents=True, exist_ok=True)

    # 从Path对象中获取文件名字符串。
    file_name = archive_file.name

    try:
        # --- 根据文件扩展名选择不同的解压策略 ---

        # 检查文件名是否以'.zip'结尾。
        if file_name.endswith('.zip'):
            # 如果是.zip文件，使用zipfile.ZipFile以只读模式('r')打开它。
            # `with`语句确保文件句柄在使用后会被自动关闭。
            with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                # 调用.extractall()方法将压缩包中的所有文件解压到指定的目标路径。
                zip_ref.extractall(extract_path)
            # 打印成功信息。
            print(".zip 文件解压成功。")

        # 检查文件名是否以一系列tar相关的扩展名结尾。
        elif file_name.endswith(('.tar.gz', '.tar', '.tgz', '.tar.bz2', '.tbz2')):
            # 如果是tar归档，使用tarfile.open打开。
            # 'r:*'是一个智能模式，它让tarfile库自动检测压缩类型（如gzip, bzip2或无压缩）。
            with tarfile.open(archive_file, 'r:*') as tar_ref:
                # 将归档中的所有文件解压到指定路径。
                tar_ref.extractall(path=extract_path)
            # 打印成功信息。
            print(".tar 归档解压成功。")

        # 检查文件名是否以'.gz'结尾。
        elif file_name.endswith('.gz'):
            # --- .gz文件的增强处理逻辑 ---
            # .gz文件通常只包含一个被压缩的文件。但有时一个.tar.gz文件可能被错误地命名为.gz。
            # 因此，我们优先尝试将其作为tar归档处理。
            try:
                # 尝试以gzipped tar模式('r:gz')打开文件。
                with tarfile.open(archive_file, 'r:gz') as tar_ref:
                    # 如果成功打开，说明它是一个gzipped tar文件，解压所有内容。
                    tar_ref.extractall(path=extract_path)
                # 打印成功识别并解压的信息。
                print(f".gz 文件被成功识别并作为 tar 归档解压。")
            # 如果tarfile在尝试读取时抛出ReadError，说明它不是一个有效的tar文件。
            except tarfile.ReadError:
                # 打印回退信息，告知用户它将被当作单个文件处理。
                print("   └── .gz 文件不是 tar 归档，作为单个文件解压...")
                # 使用Path对象的.stem属性获取文件名中去掉最后一个后缀的部分（例如 'file.txt.gz' -> 'file.txt'）。
                output_filename = archive_file.stem
                # 构建解压后输出文件的完整路径。
                output_path = extract_path / output_filename

                # 使用gzip.open以二进制读取模式('rb')打开.gz文件。
                with gzip.open(archive_file, 'rb') as f_in:
                    # 以二进制写入模式('wb')创建一个新的空文件，用于存放解压后的内容。
                    with open(output_path, 'wb') as f_out:
                        # 使用shutil.copyfileobj将解压后的数据流从输入文件(f_in)高效地复制到输出文件(f_out)。
                        shutil.copyfileobj(f_in, f_out)
                # 打印单个文件解压成功的消息。
                print(f".gz 单个文件已解压到 '{output_path.name}'。")

        # 如果文件的扩展名不匹配任何已知格式。
        else:
            # 构造一个ValueError并抛出，告知用户这是一个不支持的格式。
            raise ValueError(f"不支持的归档格式: '{archive_file.suffix}'")

    # 捕获在解压过程中可能发生的任何异常。
    except Exception as e:
        # 打印详细的错误信息，包括文件名和异常本身。
        print(f"解压文件 '{archive_file.name}' 时出错: {e}")
        # 重新抛出异常，这样调用此函数的代码就能知道操作失败了。
        raise

    # 如果所有操作都成功，返回解压目录的Path对象。
    return extract_path


def list_files_recursive(directory: Path) -> List[str]:
    """
    递归地列出指定目录下的所有文件路径。
    返回的路径是相对于所提供目录的相对路径。

    Args:
        directory (Path): 要扫描的目录的 Path 对象。

    Returns:
        List[str]: 一个包含所有文件相对路径字符串的列表。
    """
    # 这是一个列表推导式，用于高效地构建文件列表。
    # `directory.rglob('*')`会递归地查找（'r' for recursive）匹配通配符'*'（即所有项目）的路径。
    # `if p.is_file()`部分会过滤掉目录，只保留文件。
    # `p.relative_to(directory)`计算文件相对于起始目录的相对路径。
    # `str(...)`将最终的相对路径Path对象转换为字符串。
    files = [str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()]
    # 打印找到的文件总数。
    print(f"--- 在解压目录中找到 {len(files)} 个文件。 ---")
    # 返回构建好的文件列表。
    return files


def read_text_file(file_path: Path) -> str:
    """
    读取指定文本文件的内容。

    Args:
        file_path (Path): 文件的 Path 对象。

    Returns:
        str: 文件的文本内容。

    Raises:
        Exception: 如果在读取文件时发生任何错误。
    """
    try:
        # 使用`with open(...)`语句打开文件，确保文件在操作后被关闭。
        # 'r'表示以只读模式打开。
        # `encoding='utf-8'`指定使用UTF-8编码读取文件，这是最常见的文本编码。
        # `errors='ignore'`参数表示如果在解码过程中遇到无法识别的字节，就直接忽略它们，而不是抛出错误。
        # 这在处理可能包含编码问题的文件时很有用。
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            # 调用文件对象的.read()方法，读取整个文件的内容并作为一个字符串返回。
            return f.read()
    # 捕获读取文件时可能发生的任何异常（如权限错误）。
    except Exception as e:
        # 打印错误信息。
        print(f"读取文件 '{file_path}' 时出错: {e}")
        # 重新抛出异常。
        raise