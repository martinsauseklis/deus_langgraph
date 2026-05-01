from langchain.messages import AnyMessage


def _flatten_ai_content(msg: AnyMessage) -> str:
    """Return a plain-text representation of an AI message safe for summarization.

    If the message contains tool_use blocks (either as structured tool_calls or
    embedded in a list-typed content), those are converted to a human-readable
    description instead of being forwarded as raw tool_use blocks.  This prevents
    the Anthropic API from receiving tool_use ids without matching tool_result
    blocks, which causes a 400 error.
    """
    # If content is already a plain string and there are no tool_calls, return as-is.
    if isinstance(msg.content, str):
        text = msg.content
    else:
        # content is a list of blocks — extract text blocks only.
        text_parts = [
            block["text"] if isinstance(block, dict) else block.text
            for block in msg.content
            if (isinstance(block, dict) and block.get("type") == "text")
            or (hasattr(block, "type") and block.type == "text")
        ]
        text = "\n".join(text_parts)

    # Append a compact description of any tool calls so the summarizer knows
    # what actions were taken, without including raw tool_use payloads.
    tool_calls = getattr(msg, "tool_calls", None) or []
    if tool_calls:
        tool_desc = "; ".join(
            f"[called tool '{tc['name']}']" for tc in tool_calls
        )
        text = f"{text}\n{tool_desc}".strip()

    return text or "(no content)"
