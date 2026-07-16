# Explain to me how you work
**Model**: anthropic mimo-v2.5-pro
**Working Directory**: /data/agent/choucisan

## Task Description
Explain to me how you work

## Conversation
### Turn 1 (user)
Explain to me how you work

### Turn 2 (assistant)
I'm Claude Code, an AI assistant built on Anthropic's Claude models, designed to help with software engineering tasks in your terminal environment.

Here's how I work:

**Core Architecture**
I'm powered by a large language model (currently running on mimo-v2.5-pro) that processes your requests and generates responses. I operate within a conversation context where I can see your messages and my previous responses.

**Tool System**
I have access to various tools that let me interact with your system:
- **File operations**: Read, write, and edit files in your codebase
- **Search tools**: Glob for file patterns, Grep for content search
- **Execution**: Run bash commands, manage background tasks
- **Web access**: Search the web, fetch URLs
- **Task management**: Track work with todo lists, schedule recurring tasks
- **Git integration**: Work with version control, create commits and PRs

**How I Process Requests**
1. I analyze your request to understand what you need
2. I determine which tools (if any) are required
3. I execute operations, often in parallel when independent
4. I provide updates as I work
5. I summarize results when complete

**Key Capabilities**
- Code exploration and understanding across large codebases
- Bug fixing, refactoring, and feature implementation
- Multi-step task planning and execution
- Security review and best practices
- Integration with external services (GitHub, web APIs)

**Permission Model**
Tool execution follows a permission system. Some actions run automatically, while others (especially destructive ones) require your approval. This keeps you in control of what happens to your system.

**Context Management**
I maintain conversation history and can access persistent memory across sessions. When conversations get long, I summarize earlier parts to stay within context limits while preserving important details.

I'm designed to be a collaborative partner—I'll ask for clarification when needed, suggest approaches, and keep you informed about what I'm doing throughout our work together.

## Available Tools
- **Bash**: Run a shell command.
- **BashOutput**: Read output from a running background shell command.
- **Edit**: Replace text in an existing file.
- **Glob**: Find files by glob pattern.
- **Grep**: Search file contents by pattern.
- **KillBash**: Stop a running background shell command.
- **LS**: List files and directories.
- **MultiEdit**: Apply multiple text replacements to one file.
- **NotebookEdit**: Edit a Jupyter notebook cell.
- **NotebookRead**: Read a Jupyter notebook.

## Execution Trace