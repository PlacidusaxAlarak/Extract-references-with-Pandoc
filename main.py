# main.py
# 这是整个分析工具的主入口点和业务流程协调器。
# 它将各个模块（解压、解析、分析、渲染）串联起来，完成从输入一个LaTeX压缩包到输出一份HTML分析报告的完整流程。

import re  # 导入正则表达式库，用于.bbl文件的后备解析。
import logging  # 导入日志库。
from datetime import datetime  # 导入datetime库，用于在报告中生成时间戳。
from typing import List, Dict, Any, Optional  # 导入类型提示。
from pathlib import Path  # 导入Path类。
import subprocess  # 导入subprocess库，用于执行外部命令，此处为Pandoc。

# --- 导入第三方库 ---
import bibtexparser  # 导入bibtexparser库，用于专业地解析.bib文件。
# 从jinja2库导入核心类：Environment是Jinja2的中心对象，FileSystemLoader用于从文件系统加载模板，select_autoescape用于配置自动HTML转义。
from jinja2 import Environment, FileSystemLoader, select_autoescape
from langchain_core.tools import tool # 从LangChain导入tool装饰器，用于将函数声明为可供AI调用的工具。
from pydantic import BaseModel, Field # 导入Pydantic的BaseModel和Field，用于定义和验证输入数据模型。

# --- 导入本地模块 ---
from latex_parser import LatexProjectParser  # 导入我们自己编写的LaTeX项目结构解析器。
import file_writer  # 导入文件写入模块。
import archive_handler  # 导入归档处理模块。
from pandoc_analyzer import PandocCitationAnalyzer, _normalize_key  # 导入Pandoc输出的分析器和键规范化函数。

# --- 基本配置 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 全局常量定义 ---
EXTRACT_DIR = Path('./data')  # 定义解压归档文件的目标目录。
OUTPUT_HTML_FILE = 'references_analysis_report.html'  # 定义最终输出的HTML报告文件名。
JSON_OUTPUT_FILE = 'structured_document.json'  # 定义由Pandoc生成的中间JSON文件名。


class LatexAnalysisInput(BaseModel):
    """使用Pydantic为LaTeX分析工具定义输入模型，确保输入参数的类型和存在性。"""
    # 定义一个名为archive_path的字段，类型为字符串，并提供一个清晰的描述。
    archive_path: str = Field(description="必须是有效的LaTeX项目归档文件路径 (例如, .zip, .tar.gz)。")


def parse_references(bib_paths: List[Path], bbl_path: Optional[Path]) -> List[Dict[str, Any]]:
    """
    使用混合策略解析参考文献，这是一个健壮的设计，旨在最大化成功解析参考文献的概率。
    """
    # 策略 1: 优先尝试解析.bib文件。
    if bib_paths:
        logger.info(f"策略: 找到 {len(bib_paths)} 个 .bib 文件。正在使用 bibtexparser。")
        try:
            # 使用bibtexparser.load()方法加载.bib文件的内容。
            # bib_paths[0].read_text()读取第一个找到的.bib文件的文本内容。
            # `parser=...`参数指定使用一个配置好的解析器实例，`common_strings=True`可以处理月份缩写等常见字符串。
            bib_database = bibtexparser.load(bib_paths[0].read_text(encoding='utf-8'),
                                             parser=bibtexparser.bparser.BibTexParser(common_strings=True))
            structured_references = []  # 初始化一个列表来存储解析出的参考文献。
            # 遍历解析出的数据库中的每一个条目(entry)。
            for entry in bib_database.entries:
                # 将每个条目转换为一个标准格式的字典。
                structured_references.append({
                    "key": _normalize_key(entry.get('ID', 'N/A')),  # 获取并规范化引用键（ID）。
                    "inferred_title": entry.get('title', '未找到标题').strip('{}'),  # 获取标题，并去除可能存在的大括号。
                    "inferred_author": entry.get('author', '未找到作者'),  # 获取作者。
                    "content": bibtexparser.dumps([entry])  # 使用.dumps()将单个条目转回BibTeX格式的字符串，用于报告中展示原文。
                })
            logger.info(f"成功从 .bib 文件中解析了 {len(structured_references)} 条参考文献。")
            return structured_references  # 返回解析结果。
        except Exception as e:
            logger.error(f"使用 bibtexparser 解析 .bib 文件失败: {e}。正在回退到 .bbl 文件。")

    # 策略 2: 如果.bib处理不成功或不存在，则尝试解析.bbl文件。
    if bbl_path and bbl_path.exists():
        logger.info(f"策略: 未处理 .bib 文件。正在使用正则表达式解析 .bbl 文件: {bbl_path.name}")
        structured_references = []
        try:
            bbl_content = bbl_path.read_text(encoding='utf-8', errors='ignore')
            # 定义一个正则表达式来匹配`\bibitem[...]{key} content`的模式。
            pattern = re.compile(r'\\bibitem\[.*?\]\{(.*?)\}(.*?)(?=\\bibitem|$)', re.DOTALL)
            matches = pattern.findall(bbl_content) # 查找所有匹配项。
            for key, content in matches:
                content_clean = content.strip()
                # 尝试从内容中粗略地提取作者和标题，这是一种启发式方法，不保证100%准确。
                lines = [line.strip() for line in content_clean.split('\\n') if line.strip()]
                author = lines[0].split('\\newblock')[0].strip() if lines else "无法从.bbl提取作者"
                title = "无法从.bbl提取标题"
                newblock_parts = content_clean.split('\\newblock')
                if len(newblock_parts) > 1:
                    title_candidate = newblock_parts[1].strip()
                    title = title_candidate.split('\\emph{')[0].strip().strip('., ').strip('{}')
                structured_references.append({
                    "key": _normalize_key(key), "inferred_title": title,
                    "inferred_author": author, "content": content_clean
                })
            logger.info(f"成功使用正则表达式从 .bbl 文件中解析了 {len(structured_references)} 条参考文献。")
            return structured_references
        except Exception as e:
            logger.error(f"使用正则表达式解析 .bbl 文件时出错: {e}")
    return [] # 如果两种策略都失败，返回空列表。

def render_html_from_data(all_references_data: List[Dict[str, Any]], paper_title: str) -> str:
    """使用 Jinja2 模板将最终的分析数据渲染成 HTML 字符串。"""
    # 创建一个Jinja2环境实例。`loader=FileSystemLoader('.')`告诉Jinja2在当前目录下查找模板文件。
    # `autoescape=...`开启自动转义，防止跨站脚本（XSS）攻击。
    env = Environment(loader=FileSystemLoader('.'), autoescape=select_autoescape(['html', 'xml']))
    # 从环境中加载名为'report_template.html'的模板文件。
    template = env.get_template('report_template.html')
    
    # 在渲染前对数据进行一些预处理。
    for item in all_references_data:
        if item.get("citations"):
            for citation in item["citations"]:
                # 确保citation_sentence_html字段存在，即使它为空，避免模板渲染时出错。
                citation['citation_sentence_html'] = citation.get('citation_sentence', '')
    
    # 使用sorted()函数按引用键对参考文献列表进行排序，以保证每次生成的报告顺序一致。
    sorted_references = sorted(all_references_data, key=lambda x: x.get('key', ''))
    
    # 调用模板的.render()方法，传入一个包含所有动态数据的上下文字典。
    # Jinja2会用这些数据替换模板中的占位符（如{{ paper_title }}）。
    return template.render(
        paper_title=paper_title,
        sorted_references=sorted_references,
        generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@tool(args_schema=LatexAnalysisInput)
def analyze_latex_references(archive_path: str) -> str:
    """使用稳健的、基于混合解析器的方法分析 LaTeX 项目的参考文献。"""
    print(f"--- 工具: 'analyze_latex_references' (混合解析器模式) ---")
    try:
        # --- 步骤 1: 解压与解析项目结构 ---
        print("\n第 1 步: 解压归档并解析项目结构...", flush=True)
        archive_handler.extract_archive(str(archive_path), EXTRACT_DIR)  # 调用归档处理器解压文件。
        parser = LatexProjectParser(EXTRACT_DIR)  # 初始化LaTeX项目解析器，传入解压目录。
        parser.parse()  # 执行解析，此方法会填充parser对象内部的文件列表。
        if not parser.main_file:
            raise RuntimeError("找不到可供解析的主 .tex 文件。")

        # --- 步骤 2: 定位参考文献文件 ---
        print("\n第 2 步: 定位参考文献文件...", flush=True)
        bib_files = [p for name in parser.bib_file_names for p in EXTRACT_DIR.rglob(f'**/{name}.bib')]
        bbl_file = next(EXTRACT_DIR.rglob(f'{parser.main_file.stem}.bbl'), None)
        logger.info(f"找到 {len(bib_files)} 个 .bib 文件和 {'一个' if bbl_file else '零个'} .bbl 文件。")

        # --- 步骤 3: 解析参考文献内容 ---
        print("\n第 3 步: 解析参考文献...", flush=True)
        all_references = parse_references(bib_files, bbl_file) # 调用混合策略解析函数获取文献列表。
        if not all_references:
            raise ValueError("未能从 .bib 或 .bbl 文件中解析任何参考文献。")

        # --- 步骤 4: 运行Pandoc ---
        print("\n第 4 步: 运行 Pandoc 创建单一结构化文档...", flush=True)
        analyzer_json_path = EXTRACT_DIR / JSON_OUTPUT_FILE
        # 构建Pandoc命令列表：`pandoc <main_file> --to=json --output=<output_file>`
        pandoc_command = ["pandoc", str(parser.main_file.relative_to(EXTRACT_DIR)), "--to=json",
                          f"--output={JSON_OUTPUT_FILE}"]

        print(f"   └── 在目录 '{EXTRACT_DIR}' 中执行命令: {' '.join(pandoc_command)}")
        try:
            # 使用subprocess.run()执行外部Pandoc命令。
            # `check=True`: 如果命令返回非零退出码（表示错误），则抛出CalledProcessError异常。
            # `cwd=EXTRACT_DIR`: 指定在解压目录下执行命令。
            # `capture_output=True`: 捕获命令的标准输出和标准错误。
            # `text=True`, `encoding='utf-8'`: 以UTF-8编码的文本模式处理输出。
            result = subprocess.run(pandoc_command, check=True, cwd=EXTRACT_DIR, capture_output=True, text=True,
                                    encoding='utf-8')
            print(f"Pandoc 成功创建了 '{JSON_OUTPUT_FILE}'。")
            if result.stderr: # 检查Pandoc是否在标准错误流中输出了警告信息。
                logger.warning(f"Pandoc 执行时产生警告:\n{result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("未找到 Pandoc 命令。请确保 Pandoc 已安装并在系统的 PATH 中。")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Pandoc 执行失败。错误:\n{e.stderr}")

        # --- 步骤 5: 分析Pandoc输出 ---
        print("\n第 5 步: 分析结构化数据并生成报告...", flush=True)
        analyzer = PandocCitationAnalyzer(analyzer_json_path, all_references) # 初始化分析器。
        final_data = analyzer.extract_all_data() # 调用其方法提取所有引用上下文并与文献数据合并。

        # 从Pandoc的元数据中提取论文标题。
        title_meta = analyzer.data.get('meta', {}).get('title', {})
        paper_title = analyzer._get_plain_text_from_nodes(title_meta.get('c', [])) or "无标题"

        # --- 步骤 6: 渲染并保存报告 ---
        print("\n第 6 步: 渲染并保存最终的 HTML 报告", flush=True)
        total_refs = len(final_data)
        successful_extractions = sum(1 for ref in final_data if ref.get('citations'))
        print(f"--- 分析总结: 在 {total_refs} 条参考文献中，为 {successful_extractions} 条找到了引用上下文。 ---")
        
        full_html = render_html_from_data(final_data, paper_title) # 调用渲染函数生成HTML字符串。
        file_writer.save_html_report(full_html, OUTPUT_HTML_FILE) # 调用文件写入函数保存报告。

        summary = f"成功分析了 '{archive_path}'。报告已保存到 '{OUTPUT_HTML_FILE}'。"
        print(f"\n--- 工具执行成功 ---\n{summary}")
        return summary # 返回成功摘要。

    except Exception as e: # 统一的异常处理块，捕获流程中任何位置的异常。
        error_summary = f"分析过程中发生严重错误: {e}"
        print(f"--- 工具执行期间发生异常 ---\n{error_summary}")
        return error_summary # 返回错误摘要。


# --- 当此脚本作为主程序直接运行时 ---
if __name__ == "__main__":
    supported_extensions = ('.zip', '.tar', '.gz', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')
    found_archives = [p for p in Path('.').iterdir() if p.is_file() and str(p.name).endswith(supported_extensions)]
    archive_to_process = None
    
    # 这是一个简单的自动文件发现逻辑，用于方便本地测试。
    target_file_name = 'arXiv-2509.24704v1.tar.gz'

    target_file_path = Path(target_file_name)
    if target_file_path.exists(): # 优先处理指定的目标文件。
        archive_to_process = target_file_path
        print(f"找到目标归档: '{target_file_name}'。继续分析。")
    elif len(found_archives) == 1: # 如果只找到一个压缩包，就用它。
        archive_to_process = found_archives[0]
        print(f"找到单个归档文件: '{archive_to_process.name}'。开始分析。")
    elif not found_archives: # 如果一个都没找到。
        print("错误: 当前目录中未找到 LaTeX 项目归档文件。")
    else: # 如果找到多个，但目标文件又不存在。
        print(
            "错误: 找到多个归档文件，但目标文件未找到。请指定要使用的文件或只保留一个。\n")
        for f in found_archives:
            print(f"  - {f.name}")

    if archive_to_process: # 如果成功确定了要处理的文件。
        # 调用被`@tool`装饰的函数。`.invoke()`是LangChain提供的一种标准调用方式。
        # 传入的字典会自动根据`LatexAnalysisInput`模型进行验证。
        analyze_latex_references.invoke({"archive_path": str(archive_to_process)})