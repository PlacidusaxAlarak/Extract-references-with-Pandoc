# file_writer.py

from pathlib import Path


def save_html_report(content: str, file_path: str) -> None:
    """
    Safely saves string content to a specified HTML file.

    This function ensures that the parent directory of the target file exists,
    creating it if necessary. It then writes the content to the file using
    UTF-8 encoding.

    Args:
        content (str): The HTML string content to save.
        file_path (str): The full path for the target HTML file.

    Raises:
        IOError: If an I/O-related error occurs during file writing.
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Report successfully saved to: {file_path}")
    except IOError as e:
        print(f"Error saving file to '{file_path}': {e}")
        raise
