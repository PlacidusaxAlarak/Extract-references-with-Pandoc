# archive_handler.py

import zipfile
import tarfile
import gzip
import shutil
from pathlib import Path
from typing import List


def extract_archive(archive_path: str, extract_to_dir: str) -> Path:
    """
    解压指定的归档文件到目标目录。
    支持的格式: .zip, .tar, .gz, .tar.gz, .tgz, .tar.bz2, .tbz2
    此版本增强了对 .gz 文件的处理，使其更加健壮。

    Args:
        archive_path (str): 归档文件的路径。
        extract_to_dir (str): 解压到的目标目录路径。

    Returns:
        Path: 解压后目录的Path对象。

    Raises:
        FileNotFoundError: 如果归档文件不存在。
        ValueError: 如果是不支持的归档格式。
    """
    archive_file = Path(archive_path)
    extract_path = Path(extract_to_dir)

    if not archive_file.exists():
        raise FileNotFoundError(f"错误: 归档文件未找到: {archive_path}")

    print(f"--- Extracting '{archive_file.name}' to '{extract_path}'...")
    # 确保目标目录存在
    extract_path.mkdir(parents=True, exist_ok=True)

    file_name = archive_file.name

    try:
        if file_name.endswith('.zip'):
            with zipfile.ZipFile(archive_file, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(".zip file extracted successfully.")

        elif file_name.endswith(('.tar.gz', '.tar', '.tgz', '.tar.bz2', '.tbz2')):
            # tarfile 可以自动处理 gzip 和 bzip2 压缩
            with tarfile.open(archive_file, 'r:*') as tar_ref:
                tar_ref.extractall(path=extract_path)
            print(".tar archive extracted successfully.")

        elif file_name.endswith('.gz'):
            # --- 增强的 .gz 处理逻辑 ---
            # .gz 文件可能是单个压缩文件，也可能是 gzipped 的 tar 归档。
            # 优先尝试作为 tar 归档处理，以应对命名不规范的情况 (如 .tar.gz 被命名为 .gz)。
            try:
                # 尝试以 gzipped tar 模式打开
                with tarfile.open(archive_file, 'r:gz') as tar_ref:
                    tar_ref.extractall(path=extract_path)
                print(f".gz file successfully identified and extracted as a tar archive.")
            except tarfile.ReadError:
                # 如果不是有效的 tar 文件，则回退到单文件解压逻辑
                print("   └── .gz file is not a tar archive, extracting as a single file...")
                # 我们将其解压到目标目录中，文件名去掉 .gz 后缀
                output_filename = archive_file.stem
                output_path = extract_path / output_filename

                with gzip.open(archive_file, 'rb') as f_in:
                    with open(output_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                print(f".gz single file extracted to '{output_path.name}'.")

        else:
            raise ValueError(f"不支持的归档格式: '{archive_file.suffix}'")

    except Exception as e:
        print(f"Error extracting file '{archive_file.name}': {e}")
        raise

    return extract_path


def list_files_recursive(directory: Path) -> List[str]:
    """
    递归地列出指定目录下的所有文件路径（相对于该目录）。

    Args:
        directory (Path): 要扫描的目录的Path对象。

    Returns:
        List[str]: 文件路径字符串的列表。
    """
    files = [str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file()]
    print(f"--- Found {len(files)} files in the extracted directory. ---")
    return files


def read_text_file(file_path: Path) -> str:
    """
    读取指定文本文件的内容。

    Args:
        file_path (Path): 文件的Path对象。

    Returns:
        str: 文件的文本内容。

    Raises:
        Exception: 如果读取文件时发生错误。
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        raise