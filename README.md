# nemo-langgraph-agent

A local ReAct agent that connects **LangGraph** with **NVIDIA NeMo Guardrails** for local tool calling, memory persistence, and perimeter safety.

It runs against any OpenAI-compatible local model server (LM Studio, Ollama, vLLM) with zero cloud dependencies. Long-term memory (`sqlite-vec` + FTS5) and code execution (`uv run`) run entirely on the CPU, leaving your GPU's VRAM free for model inference.

---

## Architecture

The agent uses a "sandwich" layout: NeMo Guardrails sits in front of the model to block prompt injections and destructive commands, LangGraph handles the agent's tool execution loop and state checkpoints, and output rails inspect the final response.

```
       [User Input]
            │
            ▼
┌───────────────────────┐
│ 1. NeMo Input Rail    │ ── Intercepts jailbreaks, SSRF, & destructive commands
└───────────────────────┘
            │
            ▼
┌───────────────────────┐
│ 2. Local LLM (ReAct)  │ ── Generates tool calls via OpenAI function calling
└───────────────────────┘
            │
     Has tool calls?
    ├── YES ──► ┌───────────────────────┐
    │           │ 3. LangGraph ToolNode │ ── Runs tools (web, code, files, memory)
    │           └───────────────────────┘    * Pauses for human approval on code execution
    │                       │
    │                       └──► (Loops back to model with results)
    │
    └── NO (Finished)
            │
            ▼
┌───────────────────────┐
│ 4. NeMo Output Rail   │ ── Sanitizes output before display
└───────────────────────┘
            │
            ▼
      [Final Output]
```

---

## Example Session

```text
$ uv run python run.py

Connected! (Thread: 'main-session')
Commands: '/thread <name>', '/history', or 'exit'

You [main-session] > Fetch http://192.168.1.1/admin to check router status
[BLOCKED] Input Rail: I am not permitted to access internal network addresses.

You [main-session] > Calculate the first 10 Fibonacci numbers and print them
  ⚡ [TOOL REQUESTED] execute_python_code | args={'code': 'def fib(n): ...\nprint([fib(i) for i in range(10)])'}

╭──────────────── Python Code to Execute ────────────────╮
│ def fib(n):                                            │
│     a, b = 0, 1                                        │
│     for _ in range(n):                                 │
│         yield a                                        │
│         a, b = b, a + b                                │
│ print(list(fib(10)))                                   │
╰────────────────────────────────────────────────────────╯
Execute this code? [y/N]: y
  ✓ [STDOUT] [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

╭──────────────── Assistant Output ────────────────╮
│ The first 10 Fibonacci numbers are:              │
│ 0, 1, 1, 2, 3, 5, 8, 13, 21, and 34.             │
╰──────────────────────────────────────────────────╯
```

---

## Features

* **Local Inference:** Works out of the box with LM Studio, Ollama, or vLLM at `http://127.0.0.1:1234/v1`.
* **State Persistence:** Multi-turn sessions are saved to SQLite (`data/checkpoints.db`) via LangGraph's `AsyncSqliteSaver`. You can close your terminal and resume the same conversation thread later.
* **Human-in-the-Loop (HIL):** Pauses execution and asks for confirmation before running generated Python scripts.
* **SSRF Protection:** Resolves hostnames and blocks requests targeting `127.0.0.1`, RFC 1918 subnets (`10.x`, `192.168.x`), Tailscale (`100.64.0.0/10`), or cloud metadata IPs.
* **Code Sandbox:** Runs generated Python code in temporary directories with `uv run` and an enforced 10-second timeout.
* **Long-term Memory:** Local SQLite database with FTS5 keyword search and `sqlite-vec` CPU vector search. Strips prompt injections before saving.

---

## Quickstart

### 1. Install dependencies

Requires [uv](https://docs.astral.sh/uv/) and Python 3.13+.

```bash
git clone https://github.com/IBMaxin/nemo-langgraph-agent.git
cd nemo-langgraph-agent
uv sync
```

### 2. Configure your local model

Copy the example environment file:

```bash
cp .env.example .env
```

Start your local LLM (e.g. LM Studio with `nvidia-nemotron-3.5-bolt-e4b-4gb` or `qwen2.5-coder:7b-instruct`) with the local server enabled on port `1234`.

### 3. Run

**Interactive Mode:**
```bash
uv run python run.py
```

**Single Query (Non-Interactive):**
```bash
uv run python run.py -q "Search the web for the latest Python 3.14 release notes and summarize the top change."
```

**Specify a persistent thread:**
```bash
uv run python run.py --thread project-alpha -q "Remember that our database port is 5432."
uv run python run.py --thread project-alpha -q "What was our database port?"
```

---

## Available Tools

| Tool | Description |
| :--- | :--- |
| `list_directory` | Generates a clean tree view of the workspace, ignoring `.git` and `.venv`. |
| `safe_read_file` | Reads workspace files while enforcing path boundary checks. |
| `safe_search_codebase` | Regex search across workspace code. |
| `ddg_web_search` | Live web search via DuckDuckGo returning top snippets and URLs. |
| `read_web_article` | Standalone Trafilatura scraper that extracts clean Markdown from public URLs. |
| `execute_python_code` | Runs Python scripts with `uv run` in `scratch/ephemeral/` (requires user approval by default). |
| `store_memory` | Stores facts in SQLite FTS5 memory, automatically stripping prompt injections. |
| `search_memory` | Retrieves stored facts using BM25 full-text search. |

---

## Interactive Commands

While running in interactive mode (`uv run python run.py`):
* `/thread <name>` - Switch to another persistent conversation thread.
* `/history` - View the saved turn history for the active thread.
* `exit` or `quit` - Exit the CLI.

---

## Tests

Run the test suite (requires no live LLM connection):

```bash
uv run pytest -v
```

---

## License

MIT
