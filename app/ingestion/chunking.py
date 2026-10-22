import hashlib
import re


def chunk_blocks(blocks, version_id, size=700, overlap=100):
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk size/overlap")
    chunks, heading = [], []
    for source in blocks:
        pieces = [source["text"]] if source["kind"] in {"record", "table"} else re.split(r"\n\s*\n", source["text"])
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            first = piece.splitlines()[0]
            if re.match(r"^#{1,6}\s", first):
                level = len(first) - len(first.lstrip("#"))
                heading = heading[: level - 1] + [first[level:].strip()]
            section = source.get("section") or " / ".join(heading)
            width = 4000 if source["kind"] in {"table", "record"} else size
            for offset in range(0, len(piece), width - overlap):
                child = piece[offset : offset + width]
                if offset and len(child) <= overlap:
                    break
                position = len(chunks)
                chunks.append(
                    {
                        "id": hashlib.sha256(f"{version_id}:{position}".encode()).hexdigest(),
                        "position": position,
                        "text": child,
                        "section": section,
                        "page": source.get("page"),
                        "bbox": source.get("bbox"),
                        "parent_text": piece[:4000],
                        "kind": source["kind"],
                        "record": source.get("record") if offset == 0 else None,
                    }
                )
    return chunks
