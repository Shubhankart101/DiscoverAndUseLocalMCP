def collect_text(blocks) -> tuple[str, ...]:
    """Normalize MCP text-bearing objects while preserving their order."""
    output = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text is None:
            text = getattr(block, "content", None)
        if isinstance(text, str):
            output.append(text)
    return tuple(output)
