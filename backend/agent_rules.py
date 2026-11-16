"""The grounding rules every PBIBrain agent follows: the in-app chat, MCP clients, and the
workspace agents for GitHub Copilot (VS Code, Copilot CLI) and Antigravity that
``brain agent-setup`` writes.

PBIBrain has already parsed the project into a graph of exact objects and edges. An agent that
answers from that graph is fast and cannot invent a dependency; an agent that greps TMDL or
report JSON instead burns steps and guesses. These rules keep the agent on the graph.
"""

from __future__ import annotations

# Which single tool answers which question. The first match is the whole plan in most cases.
TOOL_PLAYBOOK = (
    "Which tool to call:\n"
    "- What does X depend on / use / is built from, what uses X, where is X shown, what breaks if X changes: "
    "brain_dependencies with the object's name (direction upstream, downstream or both; depth 2-3 for indirect). One call.\n"
    "- Find objects by a partial name or a topic: brain_search, then use the exact IDs it returns.\n"
    "- The formula, properties or evidence of one object: brain_object with its exact ID.\n"
    "- The effect of a proposed change: brain_impact. A neighbourhood picture: brain_graph.\n"
    "- Same or different logic across models: brain_commonality. Files edited since the scan: brain_pending_changes.\n"
    "- Counts and the list of models and reports: brain_overview."
)

GROUNDING_RULES = (
    "Answer only from PBIBrain: its tool results and any <graph> block. PBIBrain has already parsed the TMDL, "
    "model and report files of this project into a graph of exact objects and edges, so never read, grep or list "
    "project files (.tmdl, .pbir, .json, .bim, .pbip) or run commands to answer a question about the model or report. "
    "Never infer a dependency from a name or from DAX you imagine: report only edges and objects the graph returned, "
    "with their exact names. If the graph does not have it, say so in one sentence instead of guessing. "
    "Use the fewest calls: when a <graph> block or one tool result answers the question, answer at once. "
    "Do not call a tool to double-check a fact you already have. "
    "When a name is AMBIGUOUS, ask which object is meant, or scope by model, instead of picking one. "
    "Results from the snapshot (freshness.source 'snapshot', stale true) reflect the last scan: say so when it matters."
)
