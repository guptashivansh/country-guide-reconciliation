import re


class ContentChunker:
    def __init__(self, max_chunk_size=6000):
        self.max_chunk_size = max_chunk_size

    def split(self, content):
        normalized_content = content.strip()
        if not normalized_content:
            return []

        chunks = []
        current = ""
        for sentence in self._split_sentences(normalized_content):
            if len(sentence) > self.max_chunk_size:
                if current:
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._split_long_sentence(sentence))
                continue

            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > self.max_chunk_size:
                chunks.append(current.strip())
                current = sentence
            else:
                current = candidate

        if current:
            chunks.append(current.strip())

        return [{
            "chunk_index": index,
            "chunk_count": len(chunks),
            "text": chunk,
        } for index, chunk in enumerate(chunks)]

    def _split_sentences(self, content):
        sentences = re.split(r"(?<=[.!?])\s+|\n+", content)
        return [sentence.strip() for sentence in sentences if sentence.strip()]

    def _split_long_sentence(self, sentence):
        return [
            sentence[index:index + self.max_chunk_size].strip()
            for index in range(0, len(sentence), self.max_chunk_size)
            if sentence[index:index + self.max_chunk_size].strip()
        ]
