from typing import List


def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 150) -> List[str]:
    """
    Splits document text into chunks of up to `chunk_size` characters with `chunk_overlap` overlap.
    Attempts to respect line boundaries to keep code blocks and metadata lines intact.
    """
    if not text:
        return []

    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    lines = text.split("\n")
    chunks: List[str] = []
    
    current_lines: List[str] = []
    current_length = 0

    for line in lines:
        line_len = len(line) + 1  # include newline char
        
        # If adding this line exceeds chunk_size and we already have content
        if current_length + line_len > chunk_size and current_lines:
            chunk_content = "\n".join(current_lines).strip()
            if chunk_content:
                chunks.append(chunk_content)

            # Keep overlapping lines from the end of current_lines for the next chunk
            overlap_lines: List[str] = []
            overlap_length = 0
            for prev_line in reversed(current_lines):
                prev_len = len(prev_line) + 1
                if overlap_length + prev_len <= chunk_overlap:
                    overlap_lines.insert(0, prev_line)
                    overlap_length += prev_len
                else:
                    break
            
            current_lines = overlap_lines
            current_length = overlap_length

        current_lines.append(line)
        current_length += line_len

    if current_lines:
        final_chunk = "\n".join(current_lines).strip()
        if final_chunk:
            chunks.append(final_chunk)

    return chunks if chunks else [text]
