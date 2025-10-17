# latex_parser.py
# 这个文件定义了一个高级的 LaTeX 项目解析器，用于智能地发现项目中所有相关的 .tex 文件和参考文献文件。
# 它不依赖于简单的文本搜索，而是利用pylatexenc库对LaTeX源码进行真正的语法分析。

import logging  # 导入日志库，用于记录程序运行过程中的信息。
from pathlib import Path  # 导入Path类，用于处理文件路径。
from typing import List, Set, Optional  # 导入类型提示，增强代码可读性。

# --- 导入pylatexenc库，这是解析LaTeX语法的核心 ---
# LatexWalker是pylatexenc的核心类，用于遍历LaTeX源码并将其分解为节点（nodes）。
# LatexMacroNode代表一个LaTeX宏（即一个命令，如 \documentclass）。
from pylatexenc.latexwalker import LatexWalker, LatexMacroNode
# LatexNodes2Text用于将pylatexenc解析出的节点列表转换回纯文本字符串。
from pylatexenc.latex2text import LatexNodes2Text

# --- 配置日志 ---
# 设置日志的基本配置：日志级别为INFO，格式包含时间、级别和消息。
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# 获取一个名为当前模块名称的logger实例。
logger = logging.getLogger(__name__)


class LatexProjectParser:
    """
    一个高级 LaTeX 项目解析器，旨在稳健地发现所有 .tex 文件和参考文献文件。
    该解析器使用 pylatexenc 库，能够准确地处理 LaTeX 语法，而不是简单的文本匹配。
    """

    def __init__(self, base_dir: Path):
        """
        初始化解析器。

        Args:
            base_dir (Path): LaTeX 项目的根目录。
        """
        # 保存项目根目录的Path对象。
        self.base_dir = base_dir
        # 使用.is_dir()方法验证提供的路径是否确实是一个目录。
        if not self.base_dir.is_dir():
            # 如果不是目录，则抛出NotADirectoryError异常。
            raise NotADirectoryError(f"提供的路径不是一个有效的目录: {self.base_dir}")

        # --- 初始化内部状态变量 ---
        # self.main_file: 将存储找到的主.tex文件的Path对象。
        self.main_file: Optional[Path] = None
        # self.all_tex_files: 使用集合(set)来存储项目中所有找到的.tex文件的路径，集合可自动去重。
        self.all_tex_files: Set[Path] = set()
        # self.bib_file_names: 使用集合存储所有找到的.bib文件名（不含扩展名）。
        self.bib_file_names: Set[str] = set()
        # self._processed_files: 记录已处理过的文件，以防止在递归解析中陷入无限循环（例如A引用B，B又引用A）。
        self._processed_files: Set[Path] = set()

    def parse(self):
        """
        执行完整的解析工作流程，以查找所有相关的项目文件。
        这是该类的主要入口点。
        """
        # 步骤 1: 调用内部方法找到主.tex文件。
        self.main_file = self._find_main_tex_file()
        
        # 如果找不到明确的主文件，则采取备用策略。
        if not self.main_file:
            # 记录一个错误日志。
            logger.error(f"在 '{self.base_dir}' 中找不到主 .tex 文件。")
            # 尝试查找项目中的任何.tex文件作为备选方案。
            all_files = list(self.base_dir.rglob('*.tex'))
            # 如果一个.tex文件都找不到，则无法继续，直接返回。
            if not all_files:
                logger.error("项目中未找到任何 .tex 文件。")
                return
            # 将找到的第一个.tex文件作为主文件。
            self.main_file = all_files[0]
            # 记录一个警告日志，告知用户当前使用的是备选方案。
            logger.warning(f"没有明确的主文件；将使用找到的第一个文件继续: {self.main_file.name}")

        # 步骤 2: 从主文件开始进行递归解析。
        logger.info(f"从主文件开始解析项目: {self.main_file.name}")
        # 调用递归解析方法。
        self._recursive_parse(self.main_file)
        
        # 解析完成后，记录总结信息。
        logger.info(
            f"解析完成。共找到 {len(self.all_tex_files)} 个唯一的 .tex 文件和 {len(self.bib_file_names)} 个 bib 文件。 ולא")

    def _find_main_tex_file(self) -> Optional[Path]:
        r"""
        使用一套健壮的启发式规则在项目目录中查找主 .tex 文件。
        """
        # 1. 最高优先级：检查根目录是否存在名为'main.tex'的文件。
        preferred_main = self.base_dir / 'main.tex'
        if preferred_main.is_file():
            logger.info("在根目录找到 'main.tex'，将其选为主文件。")
            return preferred_main

        # 2. 搜索包含`\documentclass`命令的候选文件。
        root_candidates = []  # 存储在根目录找到的候选文件
        sub_dir_candidates = [] # 存储在子目录找到的候选文件
        # 递归搜索所有.tex文件。
        for path in self.base_dir.rglob('*.tex'):
            try:
                # 读取文件内容并检查是否包含'\\documentclass'字符串。这是一个简单但有效的判断方法。
                if '\documentclass' in path.read_text(encoding='utf-8', errors='ignore'):
                    # 判断文件是否在根目录。
                    if path.parent == self.base_dir:
                        root_candidates.append(path)
                    else:
                        sub_dir_candidates.append(path)
            except Exception:
                # 忽略任何可能出现的读取错误。
                continue

        # 3. 从候选者中选择最佳文件。
        if root_candidates:
            # 如果根目录有多个候选，优先选择常见的名称如'paper.tex'或'article.tex'。
            for preferred_name in ['paper.tex', 'article.tex']:
                for f in root_candidates:
                    if f.name.lower() == preferred_name:
                        return f
            return root_candidates[0]  # 否则返回第一个找到的候选者。

        if sub_dir_candidates:
            # 如果根目录没有，则返回子目录中的第一个候选者。
            return sub_dir_candidates[0]

        return None  # 如果没有找到任何合适的文件，返回None。

    def _recursive_parse(self, current_file: Path):
        r"""
        递归地解析一个 .tex 文件，跟踪 `\input` 和 `\include` 命令以发现所有依赖。
        """
        # 基础情况：如果文件已经被处理过，或文件不存在，则直接返回以避免重复工作和错误。
        if current_file in self._processed_files or not current_file.exists():
            return

        # 将当前文件标记为已处理，并将其添加到找到的.tex文件集合中。
        self._processed_files.add(current_file)
        self.all_tex_files.add(current_file)
        logger.info(f"  正在解析文件中的依赖: {current_file.relative_to(self.base_dir)}")

        try:
            # 读取.tex文件的全部内容。
            content = current_file.read_text(encoding='utf-8', errors='ignore')
            
            # 创建一个LatexWalker实例来解析文件内容。
            lw = LatexWalker(content)
            # 调用.get_latex_nodes()方法，它会返回一个节点列表对象(nodelist_obj)以及解析的位置信息。
            nodelist_obj, _, _ = lw.get_latex_nodes()

            # 从返回的对象中提取实际的节点列表。
            nodes = nodelist_obj.nodelist if hasattr(nodelist_obj, 'nodelist') else []

            # 遍历所有解析出的LaTeX节点。
            for node in nodes:
                # 使用.isNodeType()方法检查当前节点是否是一个宏节点（即LaTeX命令）。
                if node.isNodeType(LatexMacroNode):
                    # 如果是宏节点，获取其名称（如'input'），并使用.rstrip('*')去掉命令末尾可能存在的星号。
                    macro_name = node.macroname.rstrip('*')

                    # --- 识别并处理我们关心的特定宏 ---

                    # 1. 处理文件包含命令: \input 和 \include。
                    # 检查宏名是否是'input'或'include'，并且该节点有参数（node.nodeargs）。
                    if macro_name in ('input', 'include') and node.nodeargs:
                        # 宏的参数本身也是一个节点列表。我们使用LatexNodes2Text将其转换回纯文本字符串。
                        # node.nodeargs[0]是第一个参数，.nodelist是其内容。
                        rel_path_str = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist).strip()
                        # 很多时候\input命令中的文件名不带.tex后缀，这里我们自动补全。
                        if not rel_path_str.endswith('.tex'):
                            rel_path_str += '.tex'

                        # 将提取到的相对路径与当前文件的父目录结合，然后使用.resolve()得到一个规范化的绝对路径。
                        next_file = (current_file.parent / rel_path_str).resolve()
                        # 递归调用自身来解析这个新发现的文件。
                        self._recursive_parse(next_file)

                    # 2. 处理参考文献命令: \bibliography。
                    elif macro_name == 'bibliography' and node.nodeargs:
                        # 同样地，将参数（即.bib文件名）转换为文本。
                        bib_names_str = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist)
                        # 一个\bibliography命令可能包含多个.bib文件，用逗号分隔，所以我们用.split(',')处理。
                        for bib_name in bib_names_str.split(','):
                            # 将清理过的.bib文件名添加到集合中。
                            self.bib_file_names.add(bib_name.strip())

        except Exception as e:
            # 捕获并记录解析过程中可能发生的任何错误。
            logger.error(f"解析文件 {current_file.name} 失败: {e}")