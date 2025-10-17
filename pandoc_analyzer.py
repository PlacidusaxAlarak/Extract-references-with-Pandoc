# pandoc_analyzer.py
# 该文件负责解析由 Pandoc 生成的 JSON 格式的抽象语法树 (AST)，
# 目的是从中提取所有参考文献的引用(citation)上下文信息。

import json  # 导入json库，用于加载和解析JSON文件。
from pathlib import Path  # 导入Path类。
import re  # 导入正则表达式库。
from typing import List, Dict, Any  # 导入类型提示。


def _normalize_key(key: str) -> str:
    """
    规范化引用键 (citation key)，以便进行一致和可靠的匹配。
    
    操作:
    1. 将键字符串转换为全小写。
    2. 使用正则表达式移除所有非字母、数字、连字符或下划线的字符。
    
    这确保了在不同地方格式稍有不同的同一个引用键（如 `Smith2021` 和 `smith-2021`）能够被正确匹配。
    """
    # re.sub(pattern, repl, string)函数用于执行替换。
    # `r'[^a-z0-9\-_]'`是一个正则表达式模式：
    # `[]`定义一个字符集，`^`在字符集内部表示“非”，所以`[^...]`匹配任何不在集合内的字符。
    # `a-z0-9\-_`定义了允许的字符范围：小写字母、数字、连字符和下划线。
    # `''`是替换字符串，即删除匹配到的字符。
    return re.sub(r'[^a-z0-9\-_]', '', key.lower())


class PandocCitationAnalyzer:
    """
    一个分析器，用于处理 Pandoc 的 JSON 输出，以提取参考文献的上下文信息。
    它遍历 Pandoc AST，定位每一个引用，并记录其所在的句子、章节以及前后的句子。
    """
    def __init__(self, json_path: Path, references: List[Dict[str, Any]]):
        """
        初始化分析器。
        """
        self.json_path = json_path  # 保存Pandoc JSON文件的路径。
        self.data = self._load_json()  # 调用内部方法加载JSON数据到self.data。
        
        # 创建一个以规范化引用键为键、参考文献信息为值的字典。
        # 这提供了一个O(1)时间复杂度的快速查找表，用于后续将上下文与具体的文献条目关联起来。
        self.structured_references = {ref['key']: ref for ref in references}
        
        # 初始化一个空列表，用于存储从AST中提取的所有引用上下文实例。
        self.citations = []

    def _load_json(self) -> Dict:
        """从文件加载并解析JSON数据。"""
        # 以只读模式('r')和UTF-8编码打开JSON文件。
        with open(self.json_path, 'r', encoding='utf-8') as f:
            # json.load()方法读取文件流并将其解析为Python字典或列表。
            return json.load(f)

    def _get_plain_text_from_nodes(self, nodes: List[Dict]) -> str:
        """
        一个递归函数，将一个 Pandoc 的内联节点 (inline nodes) 列表转换为纯文本字符串。
        Pandoc AST中的文本、空格、引文等都是内联节点。
        """
        text_parts = []  # 用于收集文本片段的列表。
        if not isinstance(nodes, list):
            return ""  # 如果输入不是列表，返回空字符串以避免错误。

        for node in nodes:  # 遍历列表中的每个节点。
            # 增加一个检查，确保节点是一个字典，然后再访问其键。
            if not isinstance(node, dict):
                text_parts.append(str(node)) # 如果不是字典，安全地转换为字符串。
                continue

            # Pandoc节点通常是`{'t': 'NodeType', 'c': content}`的结构。
            node_type = node.get('t')  # 获取节点的类型，如'Str'（字符串）、'Space'（空格）等。
            
            if node_type == 'Str':
                text_parts.append(node['c'])  # 如果是字符串节点，其内容('c')就是文本，直接附加。
            elif node_type in ('Space', 'SoftBreak', 'LineBreak'):
                text_parts.append(' ')  # 对各种空格和换行，统一处理为空格。
            elif node_type == 'Cite':
                # 如果是引文节点(e.g., `[@smith2021]`)，其格式为`{'t':'Cite', 'c':[citations, inline_content]}`。
                # `inline_content`是引文在文中渲染出的文本，如`"[1]"`。我们递归调用自身来处理这部分。
                text_parts.append(self._get_plain_text_from_nodes(node['c'][1]))
            elif node_type == 'Quoted':
                # 如果是带引号的文本，其格式为`{'t':'Quoted', 'c':[QuoteType, inline_content]}`。
                quote_type = node['c'][0].get('t') # 获取引号类型（单引号或双引号）。
                quote_char = '"' if quote_type == 'DoubleQuote' else "'"
                # 递归处理引号内的内容，并在两边加上引号字符。
                text_parts.append(quote_char + self._get_plain_text_from_nodes(node['c'][1]) + quote_char)
            elif 'c' in node and isinstance(node['c'], list):
                # 对于其他包含内联内容的节点（如Emph-强调, Strong-加粗），递归处理其内容。
                text_parts.append(self._get_plain_text_from_nodes(node['c']))
        # 使用''.join()将所有文本片段高效地拼接成一个完整的字符串。
        return ''.join(text_parts)

    def _analyze_contexts_from_ast(self):
        """
        通过直接遍历 Pandoc AST (抽象语法树) 的顶层块(blocks)来分析引用上下文。
        """
        current_section = "引言"  # 设定一个默认的章节标题。
        blocks = self.data.get('blocks', []) # 获取文档的所有顶层块（如段落、标题、列表等）。

        for block in blocks:
            # 如果块是标题（Header），则更新当前章节名称。
            if block.get('t') == 'Header':
                level = block['c'][0] # 标题级别 (1, 2, ...)
                header_text = self._get_plain_text_from_nodes(block['c'][2]) # 标题的文本内容
                current_section = f"{'#' * level} {header_text}"

            # 如果块是段落（Para），这是我们要找的引用所在的主要地方。
            elif block.get('t') == 'Para':
                # 首先，将段落中的所有内联节点按句子切分。
                sentences_as_nodes = []
                current_sentence_nodes = []
                for node in block['c']: # 遍历段落中的所有内联节点。
                    current_sentence_nodes.append(node)
                    # 如果节点是字符串且包含句末标点符号，就认为一个句子结束了。
                    if node.get('t') == 'Str' and any(p in node['c'] for p in '.!?'):
                        sentences_as_nodes.append(current_sentence_nodes)
                        current_sentence_nodes = [] # 开始收集下一个句子的节点。
                if current_sentence_nodes:  # 添加段落的最后一个句子。
                    sentences_as_nodes.append(current_sentence_nodes)

                # 其次，遍历切分好的句子节点列表。
                for i, sentence_nodes in enumerate(sentences_as_nodes):
                    sentence_keys = [] # 存储当前句子中找到的所有引用键。
                    for node in sentence_nodes:
                        if node.get('t') == 'Cite':
                            # 一个Cite节点可能包含多个引用，如`[@key1; @key2]`。
                            for citation in node['c'][0]:
                                sentence_keys.append(_normalize_key(citation['citationId']))

                    # 如果当前句子中找到了引用。
                    if sentence_keys:
                        citation_sentence_text = self._get_plain_text_from_nodes(sentence_nodes) # 获取完整的句子文本。
                        pre_context_text = self._get_plain_text_from_nodes(sentences_as_nodes[i - 1]) if i > 0 else "" # 获取前一个句子作为上文。
                        post_context_text = self._get_plain_text_from_nodes(sentences_as_nodes[i + 1]) if i < len(sentences_as_nodes) - 1 else "" # 获取后一个句子作为下文。

                        # 将这个上下文与句子中找到的所有引用键关联起来。
                        for key in set(sentence_keys):  # 使用set去重，以防一个句子内多次引用同一文献。
                            self.citations.append({
                                'key': key,
                                'section': current_section,
                                'citation_sentence': citation_sentence_text.strip(),
                                'pre_context': pre_context_text.strip(),
                                'post_context': post_context_text.strip(),
                            })

    def extract_all_data(self) -> List[Dict[str, Any]]:
        """提取引用上下文，并将其与预先解析的参考文献数据合并，返回最终的完整数据结构。"""
        # 1. 调用方法，遍历AST并填充self.citations列表。
        self._analyze_contexts_from_ast()

        # 2. 将提取到的上下文信息合并到`self.structured_references`这个主数据结构中。
        for citation_context in self.citations:
            key = citation_context['key'] # 获取当前上下文关联的引用键。
            if key in self.structured_references: # 确认这个引用键存在于我们解析的参考文献列表中。
                # 如果这是第一次为该文献条目添加上下文，需要先初始化一个'citations'列表。
                if 'citations' not in self.structured_references[key]:
                    self.structured_references[key]['citations'] = []

                # 检查重复：为避免因各种原因（如重复解析）添加完全相同的引用句子，先检查一下。
                existing_sentences = {c['citation_sentence'] for c in self.structured_references[key]['citations']}
                if citation_context['citation_sentence'] not in existing_sentences:
                    # 如果不重复，则将这个上下文信息字典附加到对应文献的'citations'列表中。
                    self.structured_references[key]['citations'].append(citation_context)

        # 3. 返回合并后包含所有信息的参考文献数据，以列表形式返回。
        return list(self.structured_references.values())