def structure_for_prompt(index: dict) -> str:
    """Compact representation for system prompt — paths + symbol names only."""
    if not index:
        return "Not initialized yet"
    lines = []
    for f in index.get("files", []):
        if "error" in f:
            continue
        symbols = ", ".join(
            f"{s['name']}:{s['start_byte']}-{s['end_byte']}"
            for s in f.get("symbols", [])
        )
        line = f["path"]
        if symbols:
            line += f"  [{symbols}]"
        lines.append(line)
    return "\n".join(lines)

