# latex_parser.py

import logging
from pathlib import Path
from typing import List, Set, Optional

from pylatexenc.latexwalker import LatexWalker, LatexMacroNode
from pylatexenc.latex2text import LatexNodes2Text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class LatexProjectParser:
    """
    An advanced LaTeX project parser to robustly discover all .tex files and bibliography files.
    This parser uses pylatexenc for accurately handling LaTeX syntax.
    """

    def __init__(self, base_dir: Path):
        """
        Initializes the parser with the base directory of the LaTeX project.
        """
        self.base_dir = base_dir
        if not self.base_dir.is_dir():
            raise NotADirectoryError(f"Provided path is not a valid directory: {self.base_dir}")

        self.main_file: Optional[Path] = None
        self.all_tex_files: Set[Path] = set()
        self.bib_file_names: Set[str] = set()
        self._processed_files: Set[Path] = set()

    def parse(self):
        """
        Executes the full parsing workflow to find all relevant project files.
        """
        self.main_file = self._find_main_tex_file()
        if not self.main_file:
            logger.error(f"Could not find a main .tex file in '{self.base_dir}'.")
            # Fallback: try to find *any* .tex file if no main one is identified
            all_files = list(self.base_dir.rglob('*.tex'))
            if not all_files:
                return
            self.main_file = all_files[0]
            logger.warning(f"No clear main file; proceeding with first found: {self.main_file.name}")

        logger.info(f"Starting project parse from main file: {self.main_file.name}")
        self._recursive_parse(self.main_file)
        logger.info(
            f"Parsing complete. Found {len(self.all_tex_files)} unique .tex files and {len(self.bib_file_names)} bib files.")

    def _find_main_tex_file(self) -> Optional[Path]:
        r"""
        Finds the main .tex file in the project directory using robust heuristics.
        Priority:
        1. `main.tex` in the root.
        2. Any `.tex` file in the root containing `\documentclass`.
        3. Any `.tex` file in subdirectories containing `\documentclass`.
        """
        # High-priority check for main.tex in the root
        preferred_main = self.base_dir / 'main.tex'
        if preferred_main.is_file():
            logger.info("Found 'main.tex' in root directory, selecting it as main file.")
            return preferred_main

        # Search for candidates with \documentclass
        root_candidates = []
        sub_dir_candidates = []
        for path in self.base_dir.rglob('*.tex'):
            try:
                if '\\documentclass' in path.read_text(encoding='utf-8', errors='ignore'):
                    if path.parent == self.base_dir:
                        root_candidates.append(path)
                    else:
                        sub_dir_candidates.append(path)
            except Exception:
                continue

        if root_candidates:
            # Prefer 'paper.tex' or 'article.tex' if multiple candidates exist in root
            for preferred_name in ['paper.tex', 'article.tex']:
                for f in root_candidates:
                    if f.name.lower() == preferred_name:
                        return f
            return root_candidates[0]

        if sub_dir_candidates:
            return sub_dir_candidates[0]

        return None

    def _recursive_parse(self, current_file: Path):
        r"""
        Recursively parses a .tex file, following \input and \include commands
        to discover all project dependencies.
        """
        if current_file in self._processed_files or not current_file.exists():
            return

        self._processed_files.add(current_file)
        self.all_tex_files.add(current_file)
        logger.info(f"  Parsing dependencies in: {current_file.relative_to(self.base_dir)}")

        try:
            content = current_file.read_text(encoding='utf-8', errors='ignore')
            # Use LatexWalker to find dependencies
            lw = LatexWalker(content)
            nodelist_obj, _, _ = lw.get_latex_nodes()

            nodes = nodelist_obj
            if hasattr(nodelist_obj, 'nodelist'):
                nodes = nodelist_obj.nodelist

            for node in nodes:
                if node.isNodeType(LatexMacroNode):
                    macro_name = node.macroname.rstrip('*')

                    # Follow \input and \include
                    if macro_name in ('input', 'include') and node.nodeargs:
                        # Extract file path from the node argument
                        rel_path_str = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist).strip()
                        if not rel_path_str.endswith('.tex'):
                            rel_path_str += '.tex'

                        # Resolve the path relative to the current file
                        next_file = (current_file.parent / rel_path_str).resolve()
                        self._recursive_parse(next_file)

                    # Find bibliography files from \bibliography command
                    elif macro_name == 'bibliography' and node.nodeargs:
                        bib_names_str = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist)
                        for bib_name in bib_names_str.split(','):
                            self.bib_file_names.add(bib_name.strip())

        except Exception as e:
            logger.error(f"Failed to parse {current_file.name}: {e}")