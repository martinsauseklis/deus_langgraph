import asyncio

from langgraph.prebuilt import ToolNode

from agent.utils.logger import add_tool_logger, logger
from agent.utils.event_logger import log_event, log_tool_call, log_tool_result


def _thread_id(config: object) -> str:
    if isinstance(config, dict):
        return config.get("metadata", {}).get("thread_id", "unknown")
    return "unknown"


class LoggedToolNode(ToolNode):
    @add_tool_logger
    def invoke(self, *args, **kwargs):
        return super().invoke(*args, **kwargs)

    # NOTE: @add_tool_logger NOT used here — we do all logging manually so that
    # event logging and text logging stay in sync, and all file I/O goes through
    # asyncio.to_thread to avoid blocking the ASGI event loop.
    async def ainvoke(self, input, config=None, **kwargs):
        tid = _thread_id(config)

        await asyncio.to_thread(logger.info, "Entering node ainvoke", extra={"thread_id": tid})

        # Log each pending tool call from the last AI message.
        messages = input.get("messages", []) if isinstance(input, dict) else []
        last_ai = next(
            (m for m in reversed(messages) if getattr(m, "tool_calls", None)),
            None,
        )
        if last_ai:
            for tc in last_ai.tool_calls:
                name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                args_val = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
                await asyncio.to_thread(log_tool_call, tid, name, args_val)

        result = await super().ainvoke(input, config, **kwargs)

        # Log tool results.
        if isinstance(result, dict):
            for msg in result.get("messages", []):
                if hasattr(msg, "tool_call_id"):
                    tool_name = "?"
                    if last_ai:
                        for tc in last_ai.tool_calls:
                            tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                            if tc_id == msg.tool_call_id:
                                tool_name = tc.get("name", "?") if isinstance(tc, dict) else getattr(tc, "name", "?")
                                break
                    await asyncio.to_thread(
                        log_tool_result,
                        tid,
                        msg.tool_call_id,
                        tool_name,
                        getattr(msg, "content", ""),
                    )

        await asyncio.to_thread(logger.info, "Node result: %s", result, extra={"thread_id": tid})

        return result
