# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Development
make dev                                    # Start dev server — logs to /tmp/langgraph_dev.log
langgraph dev --config langgraph_dev.json   # Start dev server without log capture

# Testing
make test                     # Unit tests
make integration_tests        # Integration tests
make test_watch               # Watch mode

# Linting & Formatting
make lint                     # ruff + mypy + codespell
make format                   # ruff format

# Single test
python -m pytest tests/unit_tests/test_foo.py::test_name -v
```

## Architecture

This is a **LangGraph multi-agent system** that orchestrates specialized AI agents to manage Next.js project development. The graph is defined in `src/agent/graph.py` and registered via `langgraph_dev.json`.

### Agent Graph Flow

```
START → start_router ──→ setup_node → index_project
                    └──→ input_validation_node → planner_node
                                                      ↓
                              ┌── business_analyst_node ──┐
                              ├── ui_ux_node               ├── development_router → END
                              ├── developer_node           │
                              │     └── developer_tools    │
                              └── testing_node             │
                                    └── testing_tools ─────┘
```

- **start_router**: Checks `create` flag — routes new projects to setup, existing ones to validation
- **planner_node**: Uses Claude to produce a `sequence: list[NodePrompts]` — the ordered list of agents to invoke
- **development_router**: Pops the next agent from `sequence`; routes to it or `END`
- **developer_node / testing_node**: Each has a budget of `MAX_TOOL_CALLS = 25`

### State (`src/agent/utils/state.py`)

```python
class AgentState(TypedDict):
    create: bool                    # New project flag
    messages: list[AnyMessage]      # Accumulated message history
    summary: str                    # Conversation summary
    project_structure: dict         # Tree-sitter parsed code index
    tool_call_count: int            # Developer agent tool budget counter
    testing_tool_call_count: int    # Testing agent tool budget counter
    sequence: list[NodePrompts]     # Planned agent execution order
```

### Key Modules

| Path | Purpose |
|------|---------|
| `src/agent/graph.py` | Graph definition and wiring |
| `src/agent/utils/state.py` | AgentState TypedDict |
| `src/agent/utils/nodes/` | One directory per agent node |
| `src/agent/utils/nodes/*/SYSTEM_PROMPT.md` | Per-agent system prompts |
| `src/agent/utils/nodes/indexer_node/project_parser.py` | tree-sitter parser for JS/TS/TSX/CSS |
| `src/agent/utils/custom_nodes/custom_nodes.py` | `LoggedToolNode` extending LangGraph's ToolNode |
| `src/agent/utils/logger.py` | `ThreadedDateFileHandler` — logs per thread to `LOGS_DIR/YYYY/MM/DD/HH/<thread_id>.log` |

### Tools

- **Developer tools**: `ShellTool` + database tools (`check_schema`, `create_schema`, `create_table`, `insert_rows`, `query_db`)
- **Testing tools**: `ShellTool` only
- All nodes are decorated with `@add_logger` for automatic state logging

### Project Parser

`indexer_node` uses tree-sitter to parse `.js`, `.ts`, `.tsx`, `.css` files and extract symbol metadata (functions, classes, byte ranges). Skips: `node_modules`, `.next`, `.git`, `dist`, `build`, `out`, `.turbo`, `coverage`.

## Environment Variables

Required:
```
ANTHROPIC_API_KEY     # Claude API key
WORKSPACE_DIR         # Base dir for project workspaces
LOGS_DIR              # Log output directory
CONFIG_SERVER         # HTTP endpoint called by setup_node for workspace init
```

Optional:
```
LANGSMITH_API_KEY     # LangSmith tracing
LANGSMITH_PROJECT     # LangSmith project name
NPM_PATH              # Node.js npm executable (injected in Docker via langgraph.json)
PG_HOST / PG_PORT / PG_DB / PG_USER / PG_PASSWORD   # PostgreSQL for database tools
```

Copy `.env.example` to `.env` before running locally.

## Code Style

- **Docstrings**: Google style (enforced by ruff rule `D`)
- **Type checking**: mypy strict mode
- **Line length**: 88 (ruff default)
- **Python**: >=3.10 required
