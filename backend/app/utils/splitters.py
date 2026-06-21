"""
Text splitting utilities for chunking document text.
Replaces the need for the heavy langchain library.
"""

from typing import List, Optional


class RecursiveCharacterTextSplitter:
    """
    Splits text recursively by a list of characters.
    Attempts to split on the first separator. If the resulting chunks are still
    too large, it recursively splits them using the next separator.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: Optional[List[str]] = None,
    ):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        """Split incoming text and return chunks."""
        return self._split_text(text, self._separators)

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text."""
        final_chunks: List[str] = []

        # Find the appropriate separator for this text
        separator = separators[-1]
        new_separators = []

        for i, _s in enumerate(separators):
            if _s == "":
                separator = _s
                break
            if _s in text:
                separator = _s
                new_separators = separators[i + 1:]
                break

        # Actually split the text
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # Merge the splits
        good_splits = []
        for s in splits:
            if s:
                good_splits.append(s)

        merged_chunks = self._merge_splits(good_splits, separator)

        # Recursively split chunks that are still too large
        for chunk in merged_chunks:
            if len(chunk) <= self._chunk_size or not new_separators:
                final_chunks.append(chunk)
            else:
                recursive_chunks = self._split_text(chunk, new_separators)
                final_chunks.extend(recursive_chunks)

        return final_chunks

    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """Merge smaller splits into chunks of appropriate size with overlap."""
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0

        for d in splits:
            _len = len(d)
            if total + _len + (len(separator) if len(current_doc) > 0 else 0) > self._chunk_size:
                if total > 0:
                    docs.append(separator.join(current_doc))
                    
                    # Compute overlap
                    while total > self._chunk_overlap or (
                        total + _len + (len(separator) if len(current_doc) > 0 else 0) > self._chunk_size
                        and total > 0
                    ):
                        total -= len(current_doc[0]) + (len(separator) if len(current_doc) > 1 else 0)
                        current_doc.pop(0)

            current_doc.append(d)
            total += _len + (len(separator) if len(current_doc) > 1 else 0)

        if current_doc:
            docs.append(separator.join(current_doc))

        return docs
