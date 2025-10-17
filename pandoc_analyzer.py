# pandoc_analyzer.py

import json
from pathlib import Path
import re
from typing import List, Dict, Any


def _normalize_key(key: str) -> str:
    """Normalizes a citation key for consistent matching."""
    return re.sub(r'[^a-z0-9\-_]', '', key.lower())


class PandocCitationAnalyzer:
    def __init__(self, json_path: Path, references: List[Dict[str, Any]]):
        self.json_path = json_path
        self.data = self._load_json()
        # Create a dictionary for quick lookup of references by their normalized key
        self.structured_references = {ref['key']: ref for ref in references}
        self.citations = []

    def _load_json(self):
        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _get_plain_text_from_nodes(self, nodes: List[Dict]) -> str:
        """
        Converts a list of Pandoc inline nodes to a plain text string,
        now correctly handling quoted text and rendering citations.
        """
        text_parts = []
        if not isinstance(nodes, list):
            return ""

        for node in nodes:
            # --- FIX STARTS HERE ---
            # Add a check to ensure the node is a dictionary before accessing its keys.
            if not isinstance(node, dict):
                # If it's not a dict, it might be a string or other literal.
                # Safely convert it to a string and continue.
                text_parts.append(str(node))
                continue
            # --- FIX ENDS HERE ---

            node_type = node.get('t')
            if node_type == 'Str':
                text_parts.append(node['c'])
            elif node_type in ('Space', 'SoftBreak', 'LineBreak'):
                text_parts.append(' ')
            elif node_type == 'Cite':
                # Render the citation text as it appears, e.g., "[1, 2]"
                text_parts.append(self._get_plain_text_from_nodes(node['c'][1]))
            elif node_type == 'Quoted':
                # Handle quoted text, e.g., "information silos"
                quote_type = node['c'][0].get('t')
                quote_char = '"' if quote_type == 'DoubleQuote' else '\''
                text_parts.append(quote_char + self._get_plain_text_from_nodes(node['c'][1]) + quote_char)
            elif 'c' in node and isinstance(node['c'], list):
                # Recursively process other nodes that have content
                text_parts.append(self._get_plain_text_from_nodes(node['c']))
        return ''.join(text_parts)

    def _analyze_contexts_from_ast(self):
        """
        Analyzes citation contexts by traversing the Pandoc AST directly.
        This new version correctly handles multiple citations in a single sentence.
        """
        current_section = "Introduction"  # Default section
        blocks = self.data.get('blocks', [])

        for block in blocks:
            if block.get('t') == 'Header':
                level = block['c'][0]
                header_text = self._get_plain_text_from_nodes(block['c'][2])
                current_section = f"{'#' * level} {header_text}"

            elif block.get('t') == 'Para':
                # A paragraph is a list of inline nodes. We split this list into sentences.
                sentences_as_nodes = []
                current_sentence_nodes = []
                for node in block['c']:
                    current_sentence_nodes.append(node)
                    # Split into a new sentence if a terminal punctuation mark is found.
                    if node.get('t') == 'Str' and any(p in node['c'] for p in '.!?'):
                        sentences_as_nodes.append(current_sentence_nodes)
                        current_sentence_nodes = []
                if current_sentence_nodes:  # Add the last sentence if it doesn't end with punctuation
                    sentences_as_nodes.append(current_sentence_nodes)

                # Now, process the collected sentences
                for i, sentence_nodes in enumerate(sentences_as_nodes):
                    # Find all citation keys within this sentence
                    sentence_keys = []
                    for node in sentence_nodes:
                        if node.get('t') == 'Cite':
                            for citation in node['c'][0]:
                                sentence_keys.append(_normalize_key(citation['citationId']))

                    # If citations were found, create context for EACH of them
                    if sentence_keys:
                        citation_sentence_text = self._get_plain_text_from_nodes(sentence_nodes)
                        pre_context_text = self._get_plain_text_from_nodes(sentences_as_nodes[i - 1]) if i > 0 else ""
                        post_context_text = self._get_plain_text_from_nodes(sentences_as_nodes[i + 1]) if i < len(
                            sentences_as_nodes) - 1 else ""

                        # Associate this single context with ALL keys found in the sentence
                        for key in set(sentence_keys):  # Use set to avoid duplicates
                            self.citations.append({
                                'key': key,
                                'section': current_section,
                                'citation_sentence': citation_sentence_text.strip(),
                                'pre_context': pre_context_text.strip(),
                                'post_context': post_context_text.strip(),
                            })

    def extract_all_data(self) -> List[Dict[str, Any]]:
        """Extracts citation contexts and merges them with pre-parsed references."""
        self._analyze_contexts_from_ast()

        for citation_context in self.citations:
            key = citation_context['key']
            if key in self.structured_references:
                if 'citations' not in self.structured_references[key]:
                    self.structured_references[key]['citations'] = []

                # Check for duplicates before appending to avoid redundant contexts
                existing_sentences = {c['citation_sentence'] for c in self.structured_references[key]['citations']}
                if citation_context['citation_sentence'] not in existing_sentences:
                    self.structured_references[key]['citations'].append(citation_context)

        return list(self.structured_references.values())