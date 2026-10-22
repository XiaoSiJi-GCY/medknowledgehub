import re


def build_context(hits, budget, token_budget=6000):
    chosen, seen, remaining, remaining_tokens = [], set(), budget, token_budget
    for item in sorted(hits, key=lambda hit: (-hit.get("score", 0), -hit.get("authority", 0))):
        normalized = re.sub(r"\s+", "", item["text"])
        if normalized in seen or remaining < 100 or remaining_tokens < 50:
            continue
        seen.add(normalized)
        # Parent context is source text, not a generated summary. Preserve citation identity.
        text = item.get("parent_text") or item["text"]
        text = text[: min(remaining, 4000)]
        # A conservative byte-BPE upper bound, requiring no tokenizer downloads.
        encoded = text.encode("utf-8")
        if len(encoded) > remaining_tokens:
            text = encoded[:remaining_tokens].decode("utf-8", errors="ignore")
        chosen.append(dict(item, citation_id=f"S{len(chosen) + 1}", context=text))
        remaining -= len(text)
        remaining_tokens -= len(text.encode("utf-8"))
    return chosen


def detect_conflicts(hits):
    # Flag potentially inconsistent quoted values; do not resolve medical disagreements by majority vote.
    claims = {}
    for hit in hits:
        for line in hit["text"].splitlines():
            match = re.match(r"\s*([^:：|]{2,40})[:：]\s*(.{1,150})", line)
            if match:
                key, value = match.groups()
                claims.setdefault(key.strip(), {}).setdefault(value.strip(), []).append(hit["id"])
    return [
        {"topic": key, "variants": [{"text": value, "chunk_ids": ids} for value, ids in values.items()]}
        for key, values in claims.items()
        if len(values) > 1 and key not in {"name", "description", "department", "category"}
    ]
