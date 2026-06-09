"""Agent-backed content regeneration.

Lets a capable MCP client (an agent) re-generate an *already-transcribed*
episode's content using the content pipeline's real prompts, then persist the
full output set through the pipeline's existing write paths. See
``orchestrator.py`` for the host-driven state machine and ``mcp_server.py`` for
the stdio MCP tools.
"""
