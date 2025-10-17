# main.py (Final Version)

import re
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import subprocess

# Parsers
import bibtexparser
from jinja2 import Environment, FileSystemLoader, select_autoescape

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from latex_parser import LatexProjectParser
import file_writer
import archive_handler
from pandoc_analyzer import PandocCitationAnalyzer, _normalize_key

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EXTRACT_DIR = Path('./data')
OUTPUT_HTML_FILE = 'references_analysis_report.html'
JSON_OUTPUT_FILE = 'structured_document.json'


class LatexAnalysisInput(BaseModel):
    """Input model for the LaTeX analysis tool."""
    archive_path: str = Field(description="Must be a valid path to a LaTeX project archive file (e.g., .zip, .tar.gz).")


def parse_references(bib_paths: List[Path], bbl_path: Optional[Path]) -> List[Dict[str, Any]]:
    """
    Parses references using a hybrid strategy.
    1. Tries to use bibtexparser on .bib files for perfect accuracy.
    2. Falls back to a robust regex-based parser on the .bbl file.
    """
    if bib_paths:
        logger.info(f"Strategy: Found {len(bib_paths)} .bib file(s). Using bibtexparser.")
        try:
            bib_database = bibtexparser.load(bib_paths[0].read_text(encoding='utf-8'),
                                             parser=bibtexparser.bparser.BibTexParser(common_strings=True))
            structured_references = []
            for entry in bib_database.entries:
                structured_references.append({
                    "key": _normalize_key(entry.get('ID', 'N/A')),
                    "inferred_title": entry.get('title', 'Title not found').strip('{}'),
                    "inferred_author": entry.get('author', 'Author not found'),
                    "content": bibtexparser.dumps([entry])
                })
            logger.info(f"Successfully parsed {len(structured_references)} references from .bib files.")
            return structured_references
        except Exception as e:
            logger.error(f"Failed to parse .bib files with bibtexparser: {e}. Falling back to .bbl.")

    if bbl_path and bbl_path.exists():
        logger.info(f"Strategy: No .bib file processed. Parsing .bbl file with regex: {bbl_path.name}")
        structured_references = []
        try:
            bbl_content = bbl_path.read_text(encoding='utf-8', errors='ignore')
            pattern = re.compile(r'\\bibitem\[.*?\]\{(.*?)\}(.*?)(?=\\bibitem|$)', re.DOTALL)
            matches = pattern.findall(bbl_content)
            for key, content in matches:
                content_clean = content.strip()
                lines = [line.strip() for line in content_clean.split('\\n') if line.strip()]
                author = lines[0].split('\\newblock')[0].strip() if lines else "Author not extracted"
                title = "Title not extracted from .bbl"
                newblock_parts = content_clean.split('\\newblock')
                if len(newblock_parts) > 1:
                    title_candidate = newblock_parts[1].strip()
                    title = title_candidate.split('\\emph{')[0].strip().strip('., ').strip('{}')
                structured_references.append({
                    "key": _normalize_key(key), "inferred_title": title,
                    "inferred_author": author, "content": content_clean
                })
            logger.info(f"Successfully parsed {len(structured_references)} references from .bbl file using regex.")
            return structured_references
        except Exception as e:
            logger.error(f"Error parsing .bbl file with regex: {e}")
    return []


def render_html_from_data(all_references_data: List[Dict[str, Any]], paper_title: str) -> str:
    """Renders the final analysis data into an HTML string using a Jinja2 template."""
    env = Environment(loader=FileSystemLoader('.'), autoescape=select_autoescape(['html', 'xml']))
    template = env.get_template('report_template.html')
    for item in all_references_data:
        if item.get("citations"):
            for citation in item["citations"]:
                citation['citation_sentence_html'] = citation.get('citation_sentence', '')
    sorted_references = sorted(all_references_data, key=lambda x: x.get('key', ''))
    return template.render(
        paper_title=paper_title,
        sorted_references=sorted_references,
        generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


@tool(args_schema=LatexAnalysisInput)
def analyze_latex_references(archive_path: str) -> str:
    """Analyzes LaTeX project references using a robust, hybrid parser-based method."""
    print(f"--- Tool: 'analyze_latex_references' (Hybrid Parser Mode) ---")
    try:
        print("\nStep 1: Extracting archive and parsing project structure...", flush=True)
        archive_handler.extract_archive(str(archive_path), EXTRACT_DIR)
        parser = LatexProjectParser(EXTRACT_DIR)
        parser.parse()
        if not parser.main_file:
            raise RuntimeError("Could not find a main .tex file to begin parsing.")

        print("\nStep 2: Locating bibliography files...", flush=True)
        bib_files = [p for name in parser.bib_file_names for p in EXTRACT_DIR.rglob(f'**/{name}.bib')]
        bbl_file = next(EXTRACT_DIR.rglob(f'{parser.main_file.stem}.bbl'), None)
        logger.info(f"Found {len(bib_files)} .bib file(s) and {'a' if bbl_file else 'no'} .bbl file.")

        print("\nStep 3: Parsing references...", flush=True)
        all_references = parse_references(bib_files, bbl_file)
        if not all_references:
            raise ValueError("Failed to parse any references from .bib or .bbl files.")

        print("\nStep 4: Running Pandoc to create a single structured document...", flush=True)
        analyzer_json_path = EXTRACT_DIR / JSON_OUTPUT_FILE
        pandoc_command = ["pandoc", str(parser.main_file.relative_to(EXTRACT_DIR)), "--to=json",
                          f"--output={JSON_OUTPUT_FILE}"]

        print(f"   └── Executing command: {' '.join(pandoc_command)} in directory '{EXTRACT_DIR}'")
        try:
            result = subprocess.run(pandoc_command, check=True, cwd=EXTRACT_DIR, capture_output=True, text=True,
                                    encoding='utf-8')
            print(f"Pandoc successfully created '{JSON_OUTPUT_FILE}'.")
            if result.stderr:
                logger.warning(f"Pandoc produced warnings:\n{result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("Pandoc command not found. Please ensure Pandoc is installed and in your system's PATH.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Pandoc execution failed. Error:\n{e.stderr}")

        print("\nStep 5: Analyzing structured data and generating report...", flush=True)
        analyzer = PandocCitationAnalyzer(analyzer_json_path, all_references)
        final_data = analyzer.extract_all_data()

        title_meta = analyzer.data.get('meta', {}).get('title', {})
        paper_title = analyzer._get_plain_text_from_nodes(title_meta.get('c', [])) or "Untitled"

        print("\nStep 6: Render and save the final HTML report", flush=True)
        total_refs = len(final_data)
        successful_extractions = sum(1 for ref in final_data if ref.get('citations'))
        print(f"--- Analysis Summary: Found contexts for {successful_extractions} out of {total_refs} references. ---")
        full_html = render_html_from_data(final_data, paper_title)
        file_writer.save_html_report(full_html, OUTPUT_HTML_FILE)

        summary = f"Successfully analyzed '{archive_path}'. Report saved to '{OUTPUT_HTML_FILE}'."
        print(f"\n--- Tool execution successful ---\n{summary}")
        return summary

    except Exception as e:
        error_summary = f"A critical error occurred during analysis: {e}"
        print(f"--- Exception during tool execution ---\n{error_summary}")
        return error_summary


if __name__ == "__main__":
    supported_extensions = ('.zip', '.tar', '.gz', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')
    found_archives = [p for p in Path('.').iterdir() if p.is_file() and str(p.name).endswith(supported_extensions)]
    archive_to_process = None
    target_file_name = 'arXiv-2507.01903v2.tar.gz'

    target_file_path = Path(target_file_name)
    if target_file_path.exists():
        archive_to_process = target_file_path
        print(f"Found target archive: '{target_file_name}'. Proceeding with analysis.")
    elif len(found_archives) == 1:
        archive_to_process = found_archives[0]
        print(f"Found a single archive: '{archive_to_process.name}'. Starting analysis.")
    elif not found_archives:
        print("Error: No LaTeX project archive found in the current directory.")
    else:
        print(
            "Error: Found multiple archives and the target file was not found. Please specify which one to use or leave only one.")
        for f in found_archives:
            print(f"  - {f.name}")

    if archive_to_process:
        analyze_latex_references.invoke({"archive_path": str(archive_to_process)})