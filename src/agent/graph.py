from langchain.agents import create_agent
from langgraph.graph import StateGraph, START, END, add_messages
from typing import TypedDict, Annotated
from langchain.messages import AnyMessage, AIMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_anthropic import ChatAnthropic
from langchain_core.messages.utils import count_tokens_approximately
from langchain_community.tools import ShellTool
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command
from pydantic import BaseModel, Field
import asyncio
import aiohttp
import os
import json

from src.tools.code_edit_tool.project_parser import run_indexer

NPM_PATH = os.getenv("NPM_PATH")
CONFIG_SERVER = os.getenv("CONFIG_SERVER")
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR")
MAX_TOKEN_COUNT_TO_TRIGGER_SUMMARY = 5000
MAX_TOOL_CALLS = 25


sonnet = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=True,
    max_retries=2,
)

model = ChatAnthropic(
    model_name="claude-sonnet-4-6",
    streaming=False,
    effort="medium",
    disable_streaming=True,
    tags=["langsmith:nostream"]
)

sonnet_with_tools = sonnet.bind_tools([ShellTool()])
summarization_model = model.bind(max_tokens=500)


class AgentState(TypedDict):
    create: bool
    messages: Annotated[list[AnyMessage], add_messages]
    summary: str
    project_structure: dict  # full index, not injected raw into prompt
    tool_call_count: int
    testing_tool_call_count: int  # separate budget for testing agent

class SendToDev(BaseModel):
    send_to_dev: bool = Field(description="If the input contains instructions to dev about failed tests, this should be true. If not - false")


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


def summarize_conversation(state: AgentState):
    summary = state.get("summary", "")
    if summary:
        summary_message = (
            f"This is a summary of the conversation to date: {summary}\n\n"
            "Extend the summary by taking into account the new messages above:"
        )
    else:
        summary_message = "Create a summary of the conversation above:"

    # Only include human and AI messages; tool messages (tool_result) are skipped.
    # AI messages are flattened to plain text so no tool_use blocks reach the API.
    messages = []
    for msg in state["messages"]:
        if msg.type == "human":
            messages.append({"type": "human", "content": msg.content})
        elif msg.type == "ai":
            messages.append({"type": "ai", "content": _flatten_ai_content(msg)})

    messages.append({"type": "human", "content": summary_message})

    response = summarization_model.invoke(messages)
    response.id = f"do-not-render-{response.id}"
    delete_messages = [RemoveMessage(id=m.id) for m in state["messages"][:-2]]
    return {"summary": response.content, "messages": delete_messages}


def is_create(state: AgentState):
    if state.get("create"):
        return "setup"
    if count_tokens_approximately(state["messages"]) > MAX_TOKEN_COUNT_TO_TRIGGER_SUMMARY:
        return "summarization_node"
    return "business_analyst"

async def setup(state: AgentState, config: RunnableConfig):
    metadata = config.get("metadata")
    request_body = {
        "thread_id": metadata.get("thread_id"),
        "config_name": metadata.get("config_name"),
        "config_author": metadata.get("config_author"),
    }
    async with aiohttp.ClientSession(CONFIG_SERVER) as session:
        async with session.post("/create", json=request_body) as response:
            return {
                "messages": [AIMessage(content="The setup is done. You can run the server.")],
            }


async def business_analyst_node(state: AgentState, config: RunnableConfig) -> AgentState:
    response = await sonnet.ainvoke(
        input=[
            SystemMessage("""You are a business analyst that translates customers' needs
into specific technical tasks to be passed to the UI/UX engineer.
                          Keep in mind that we are working currently on an existing Next.js
                          project. Don't assume anything else or offer to work on anything other.
                          Senior developer will have a context of the app, so you don't need to explain
                          the Next.js part."""),
            AIMessage(content=f"Conversation summary so far: {state.get('summary', '')}"),
            *state["messages"],
        ]
    )
    msg = AIMessage(response.content)
    msg.name = "business_analyst"
    return {
        "messages": [msg],
        "tool_call_count": 0,  # reset budget for each new user turn
    }


async def ui_ux_engineer(state: AgentState, config: RunnableConfig) -> AgentState:
    response = await sonnet.ainvoke(
        input=[
            SystemMessage("""You are a master UI/UX engineer. Based on the business analyst's
input, provide an outline of UI libraries and layouts the senior developer must use.
The project is a Next.js app."""),
            *state["messages"],
            HumanMessage("proceed"),
        ]
    )
    msg = AIMessage(response.content)
    msg.name = "ui_ux_engineer"
    return {"messages": [msg]}


async def senior_developer(state: AgentState, config: RunnableConfig) -> AgentState:
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    remaining = MAX_TOOL_CALLS - state.get("tool_call_count", 0)
    sen_dev = sonnet_with_tools if remaining > 0 else sonnet

    response = await sen_dev.ainvoke(
        input=[
            SystemMessage(f"""You are a master senior developer working exclusively in {PROJ_PATH}.
You must NEVER operate outside this directory under any circumstances.
Before using the shell tool, always verify you are within this subdirectory.
You may work in nested directories, but NEVER in parent directories.

Do NOT RUN any `.sh` files — those are strictly for the user to execute.
The project is a Next.js project.

---

## Budget: {remaining} tool calls remaining
- Max 3 calls for reading/lookup
- Remaining calls are for edits + build
After each tool call, ask yourself: "Can I act now?"
- If YES → act immediately (do not gather more context)
- If NO and you've used 3 lookups → STOP and tell the user what is missing

---

## Source Files Only
You may ONLY edit source files.

NEVER modify:
- `.next/`
- `out/`
- `dist/`
- or any build output directories

These are generated artifacts and will be overwritten.

---

## Project Structure (MANDATORY FIRST STEP)
{structure_for_prompt(state.get("project_structure", {}))}

You MUST consult this before ANY file operation.

It provides:
- exact file paths
- exact byte ranges (`start_byte`, `end_byte`)

---

## Reading Files — STRICT dd RULES

You may ONLY read files using `dd` with exact byte ranges:

    dd bs=1 skip=<start_byte> count=<end_byte - start_byte> if=<file>

### ALL of the following are REQUIRED:
1. `skip` MUST equal `start_byte`
2. `count` MUST equal exactly `(end_byte - start_byte)`
3. `bs=1` MUST always be set
4. `count` is REQUIRED — never omit it
5. `skip=0` is FORBIDDEN unless:
   - the symbol truly starts at byte 0
   - AND `count` is a small, precise range

### STRICTLY FORBIDDEN:
- reading entire files
- large arbitrary ranges
- `cat`, `head`, or similar commands
- exploratory searching

---

## When a Symbol is NOT in the Project Structure

### Case 1: Known exact string
You MAY run:
    grep -bo "exact string" path/to/file

This returns ONLY byte offsets (no content).

Then:
- Use `dd` with a SMALL, precise `count`
- Read ONLY minimal surrounding context

### Case 2: Unknown location / exploratory search needed
STOP immediately.

Do NOT:
- grep broadly
- scan files
- guess locations

Instead:
→ Inform the user the symbol is missing from the project structure  
→ Ask them to regenerate the index

---

## Editing Files — Surgical Only

- ALL edits must use exact byte ranges from the structure or lookup
- NEVER rewrite entire files
- NEVER make broad or approximate edits

Precision is mandatory.

---

## Package Management (NON-INTERACTIVE ONLY)

Allowed:
    npm install <package> --save
    npm install <package> --save-dev

If modifying dependencies manually:
1. Edit `package.json` using exact byte ranges
2. Then run:
       npm install

### STRICTLY FORBIDDEN (will hang the session):
- `npm init`
- `npx create-*`
- ANY interactive command

---

## shadcn/ui Components — MANUAL INSTALL ONLY

NEVER use `npx shadcn` in any form — it is interactive and will hang the session
regardless of flags (`--yes`, `--overwrite`, `--silent` do not prevent all prompts).

### Step 1: Install peer dependencies (non-interactive)

Install only the Radix primitives actually needed by the components you are adding:

    npm install <radix-packages> class-variance-authority clsx tailwind-merge --save

Radix primitive mapping:
- card, button, badge, input, label, separator, table → no Radix dep needed
- select → @radix-ui/react-select
- form → react-hook-form @hookform/resolvers zod
- radio-group → @radix-ui/react-radio-group
- dialog → @radix-ui/react-dialog
- dropdown-menu → @radix-ui/react-dropdown-menu
- tabs → @radix-ui/react-tabs
- tooltip → @radix-ui/react-tooltip
- checkbox → @radix-ui/react-checkbox
- switch → @radix-ui/react-switch
- avatar → @radix-ui/react-avatar
- popover → @radix-ui/react-popover
- scroll-area → @radix-ui/react-scroll-area
- sheet → @radix-ui/react-dialog  (same dep as dialog)
- progress → @radix-ui/react-progress
- slider → @radix-ui/react-slider
- accordion → @radix-ui/react-accordion

### Step 2: Fetch and write each component file directly

Use curl to download the component source from the shadcn registry and write it
to the correct path — no interactivity, no prompts:

    mkdir -p {PROJ_PATH}/src/components/ui
    curl -s https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/www/registry/new-york/ui/<component>.tsx \
      -o {PROJ_PATH}/src/components/ui/<component>.tsx

Repeat for each component. Examples:

    curl -s https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/www/registry/new-york/ui/button.tsx \
      -o {PROJ_PATH}/src/components/ui/button.tsx

    curl -s https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/www/registry/new-york/ui/card.tsx \
      -o {PROJ_PATH}/src/components/ui/card.tsx

    curl -s https://raw.githubusercontent.com/shadcn-ui/ui/main/apps/www/registry/new-york/ui/input.tsx \
      -o {PROJ_PATH}/src/components/ui/input.tsx

### Step 3: Ensure the cn() utility exists

Check whether `{PROJ_PATH}/src/lib/utils.ts` exists in the project structure.
If it is missing, create it with exactly this content:

    import {{ clsx, type ClassValue }} from "clsx"
    import {{ twMerge }} from "tailwind-merge"
    export function cn(...inputs: ClassValue[]) {{
      return twMerge(clsx(inputs))
    }}

### Step 4: Verify tailwind.config includes the component paths

The `content` array in `tailwind.config.ts` (or `.js`) MUST include:
    "./src/components/**/*.{{js,ts,jsx,tsx}}"

If it is missing, add it using exact byte ranges from the project structure.

### STRICTLY FORBIDDEN:
- `npx shadcn@latest add ...` in any form, with any flags
- `npx shadcn add ...` in any form
- Any shadcn CLI command whatsoever
- Any command that may trigger an interactive prompt

---

## End-of-Session Requirement (MANDATORY)

You MUST run:

    npm run build

### Completion criteria:
- Build MUST succeed
- ALL compile/type errors MUST be fixed

If the build fails:
→ Diagnose and fix ALL errors before stopping

You are NOT done until the build passes.
"""),
            *state["messages"],
            HumanMessage("proceed"),
        ]
    )

    response.name = "senior_developer"
    return {
        "messages": [response],
        "tool_call_count": state.get("tool_call_count", 0) + len(response.tool_calls or []),
    }

async def index_project(state: AgentState, config: RunnableConfig) -> AgentState:
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    project_structure = await asyncio.to_thread(
        run_indexer, PROJ_PATH, f"{PROJ_PATH}/ts_index.json"
    )
    if state.get("create"):
        return Command(
            goto=END,
            update={
                "project_structure": project_structure,
                "tool_call_count": 0,
                "create": False
                }
        )
    
    return Command(
        goto="testing",
        update={
            "project_structure": project_structure,
            "tool_call_count": 0,
        })

async def testing(state: AgentState, config: RunnableConfig) -> AgentState:
    PROJ_PATH = f"{WORKSPACE_DIR}/{config['metadata']['thread_id']}"
    thread_id = config['metadata']['thread_id']

    remaining = MAX_TOOL_CALLS - state.get("testing_tool_call_count", 0)
    tester = sonnet_with_tools if remaining > 0 else sonnet

    response = await tester.ainvoke(
        input=[
            SystemMessage(f"""You are a senior testing engineer. Your task is to follow what the senior_developer
has developed and write thorough, quickly runnable Playwright tests. Tests should be stored in
{PROJ_PATH}/tests directory. Structure the testing according to best practices.

Make a plan first. Then proceed with writing the tests. Always check what tests are already
in the tests directory as you might have written something in previous runs.

After writing is done (meaning that for everything the senior dev has functionally and visually
changed or added in the code, there is a test for it), run the tests.

Also make sure the whole app is covered — compare what tests you have generated against
the project structure: {state.get("project_structure", "The structure is missing")}.
Use the shell tool for that, capture the output and neatly report the outcomes.
If a test ran successfully, output nothing. If there were errors, reply with a message
of instructions that senior_developer should fix.

---

## Budget: {remaining} tool calls remaining
- Max 3 calls for reading/lookup
- Remaining calls are for writing tests + running them
After each tool call, ask yourself: "Can I act now?"
- If YES → act immediately (do not gather more context)
- If NO and you've used 3 lookups → STOP and tell the user what is missing

---

## Dev Server Management (MANDATORY BEFORE RUNNING TESTS)

Before running any tests, you MUST determine whether a dev server is already running
for this project. Follow these steps exactly:

### Step 1 — Check if server is already running

Make a GET request to:

    GET {CONFIG_SERVER}/port/{thread_id}

The response will be:
- `{{ "port": <number> }}` — server is running on that port
- `{{ "port": null }}` — no server is currently running

**Record this initial state.** You will need it after testing is complete.

### Step 2 — Start server if not running

If `port` was `null` in Step 1, start the server:

    GET {CONFIG_SERVER}/start_dev_server/{thread_id}

The response will contain `{{ "server_port": <number> }}`. Use this port as the base URL
for all Playwright tests (e.g. `{CONFIG_SERVER}`).

Wait a few seconds after starting before running tests to allow the server to boot.

If `port` was already set in Step 1, use that port directly — do NOT start a new server.

### Step 3 — Run tests

Run Playwright tests using the LOCAL binary ONLY:

    {PROJ_PATH}/node_modules/.bin/playwright test --reporter=line

### Step 4 — Stop server only if YOU started it

- If the server was **already running** before Step 1 (port was not null): **leave it running**.
- If YOU started it in Step 2 (port was null): stop it after testing:

        GET {CONFIG_SERVER}/stop_dev_server/{thread_id}

### STRICTLY FORBIDDEN for server management:
- Starting the server manually via shell commands
- Using `npm run dev`, `next dev`, or any direct process spawning
- Stopping a server that was already running before you began
- Skipping the initial port check

---

## Source Files Only
You may ONLY create or edit test files inside {PROJ_PATH}/tests.

Do NOT RUN any `.sh` files — those are strictly for the user to execute.

NEVER modify:
- `.sh` files of any kind
- `.next/`
- `out/`
- `dist/`
- or any build output directories

---

## Project Structure (MANDATORY FIRST STEP)
{structure_for_prompt(state.get("project_structure", {}))}

You MUST consult this before ANY file operation.

It provides:
- exact file paths
- exact byte ranges (`start_byte`, `end_byte`)

---

## Reading Files — STRICT dd RULES

You may ONLY read files using `dd` with exact byte ranges:

    dd bs=1 skip=<start_byte> count=<end_byte - start_byte> if=<file>

### ALL of the following are REQUIRED:
1. `skip` MUST equal `start_byte`
2. `count` MUST equal exactly `(end_byte - start_byte)`
3. `bs=1` MUST always be set
4. `count` is REQUIRED — never omit it
5. `skip=0` is FORBIDDEN unless:
   - the symbol truly starts at byte 0
   - AND `count` is a small, precise range

### STRICTLY FORBIDDEN:
- reading entire files
- large arbitrary ranges
- `cat`, `head`, or similar commands
- exploratory searching

---

## When a Symbol is NOT in the Project Structure

### Case 1: Known exact string
You MAY run:
    grep -bo "exact string" path/to/file

This returns ONLY byte offsets (no content).

Then:
- Use `dd` with a SMALL, precise `count`
- Read ONLY minimal surrounding context

### Case 2: Unknown location / exploratory search needed
STOP immediately.

Do NOT:
- grep broadly
- scan files
- guess locations

Instead:
→ Inform the user the symbol is missing from the project structure
→ Ask them to regenerate the index

---

## Checking Existing Tests (MANDATORY BEFORE WRITING)

To check what test files already exist, use ONLY:

    find {PROJ_PATH}/tests -name "*.spec.ts" -o -name "*.test.ts" 2>/dev/null

This returns file paths only — no content. Then read specific files with `dd`.

### STRICTLY FORBIDDEN for exploration:
- `ls` or any `ls` variant
- `cat`, `head`, `tail`
- Chained commands with `&&` or `;` combining multiple discovery steps
- ANY command whose sole purpose is environment discovery

---

## Writing Test Files

- Write test files using standard file write commands (e.g. `tee`, `cat >`)
- NEVER overwrite existing tests blindly — read them first with `dd`
- Keep each test file focused on a single page or feature area

---

## Running Tests

Run Playwright tests using the LOCAL binary ONLY:

    {PROJ_PATH}/node_modules/.bin/playwright test --reporter=line

### STRICTLY FORBIDDEN:
- `npx ...` — forbidden for ALL commands in this node, it will hang waiting for package resolution
- `npx playwright ...` — specifically forbidden
- `which playwright`, `playwright --version`, or any probe/version check commands
- ANY environment discovery commands before running tests
- ANY interactive command
- Chained multi-step discovery commands (`cmd1 && cmd2 || cmd3`)

If the binary is not found at that path, STOP and report to the user — do NOT
fall back to `npx` or any other alternative.

If a command hangs for any reason, STOP immediately and report to the user — do NOT retry.

As a response you should return all the tests that were run and the outcome.
"""),
            *state.get("messages", []),
            HumanMessage("gather context from previous messages and proceed")
        ]
    )
    
    response.name = "testing_engineer"

    return {
        "messages": [response],
        "testing_tool_call_count": state.get("testing_tool_call_count", 0) + len(response.tool_calls or []),
    }

async def testing_router(state: AgentState):
    """Single router for the testing node.
    
    Priority 1: if the last message has pending tool calls, go to testing_tools.
    Priority 2: use structured output to decide whether to loop back to senior_developer.
    
    Combining both decisions here avoids the duplicate add_conditional_edges error
    and ensures tool_use blocks always have matching tool_result blocks before we
    invoke the structured model.
    """
    last_msg = state.get("messages")[-1]

    # If the testing engineer made tool calls, execute them first.
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"

    # No pending tool calls — safe to invoke structured model.
    # Strip any residual tool_calls metadata so the Anthropic API never receives
    # a tool_use block without a following tool_result block.
    structured_model = sonnet.with_structured_output(SendToDev)
    clean_msg = AIMessage(
        content=last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content),
        name=getattr(last_msg, "name", None),
    )
    structured = await structured_model.ainvoke(input=[
        clean_msg,
        HumanMessage("Evaluate the input and return a proper value.")
    ])

    if structured.send_to_dev:
        return "senior_developer"

    # Testing run is complete — reset the budget for the next cycle.
    # We return END here; the reset happens via the state update in the node itself,
    # but we need to signal it. Instead we handle the reset directly in the router
    # by returning a sentinel that maps to a thin reset node.
    return "reset_testing_budget"


async def reset_testing_budget(state: AgentState) -> AgentState:
    """Resets the testing tool call counter after a completed testing cycle."""
    return {"testing_tool_call_count": 0}


tools = ToolNode([ShellTool()])

workflow = StateGraph(AgentState)
workflow.add_node("setup", setup)
workflow.add_node("business_analyst", business_analyst_node)
workflow.add_node("ui_ux_engineer", ui_ux_engineer)
workflow.add_node("senior_developer", senior_developer)
workflow.add_node("tools", tools)
workflow.add_node("testing_tools", tools)
workflow.add_node("summarization_node", summarize_conversation)
workflow.add_node("index_project", index_project)
workflow.add_node("testing", testing)
workflow.add_node("reset_testing_budget", reset_testing_budget)

workflow.add_conditional_edges(START, is_create, {
    "setup": "setup",
    "summarization_node": "summarization_node",
    "business_analyst": "business_analyst",
})
workflow.add_conditional_edges("senior_developer", tools_condition, {
    "tools": "tools",
    "__end__": "index_project",
})
# Single conditional edge from testing — handles both tool dispatch and
# back_to_developer logic to avoid the duplicate-edge error.
workflow.add_conditional_edges("testing", testing_router, {
    "tools": "testing_tools",
    "senior_developer": "senior_developer",
    "reset_testing_budget": "reset_testing_budget",
})
workflow.add_edge("summarization_node", "business_analyst")
workflow.add_edge("business_analyst", "ui_ux_engineer")
workflow.add_edge("ui_ux_engineer", "senior_developer")
workflow.add_edge("tools", "senior_developer")
workflow.add_edge("testing_tools", "testing")
workflow.add_edge("setup", "index_project")
workflow.add_edge("reset_testing_budget", END)

graph = workflow.compile()