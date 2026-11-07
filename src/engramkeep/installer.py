"""Agent integration planner.

The 0.1.0 installer is intentionally a dry run. It never edits agent
configuration, never writes outside the repository, and never creates
symlinks or junctions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentPlan:
    """Describes where an agent reads instructions and skills."""

    name: str
    display_name: str
    targets: tuple[str, ...]
    notes: str = ""
    extra: tuple[str, ...] = field(default_factory=tuple)


AGENT_PLANS: dict[str, AgentPlan] = {
    "opencode": AgentPlan(
        name="opencode",
        display_name="OpenCode",
        targets=(
            "~/.config/opencode/AGENTS.md",
            "~/.config/opencode/skills/engramkeep/SKILL.md",
        ),
        notes="Copy templates/agents/AGENTS.md and skills/engramkeep/SKILL.md.",
    ),
    "claude-code": AgentPlan(
        name="claude-code",
        display_name="Claude Code",
        targets=(
            "~/.claude/CLAUDE.md",
            "~/.claude/skills/engramkeep/SKILL.md",
        ),
        notes="Append the managed block from templates/rules/claude-code.md to CLAUDE.md.",
    ),
    "codex": AgentPlan(
        name="codex",
        display_name="OpenAI Codex",
        targets=(
            "~/.codex/AGENTS.md",
            "AGENTS.md",
        ),
        notes="Use a global AGENTS.md or a project-level AGENTS.md.",
    ),
    "cursor": AgentPlan(
        name="cursor",
        display_name="Cursor",
        targets=(
            ".cursor/rules/engramkeep.mdc",
            "AGENTS.md",
        ),
        notes="Copy templates/rules/cursor.mdc into the project's .cursor/rules directory.",
    ),
    "windsurf": AgentPlan(
        name="windsurf",
        display_name="Windsurf",
        targets=(
            ".windsurf/rules/engramkeep.md",
            "AGENTS.md",
        ),
        notes="Copy templates/rules/windsurf.md into the project's .windsurf/rules directory.",
    ),
    "gemini-cli": AgentPlan(
        name="gemini-cli",
        display_name="Gemini CLI",
        targets=(
            "~/.gemini/GEMINI.md",
            "GEMINI.md",
            "AGENTS.md",
        ),
        notes="Prefer AGENTS.md when the agent supports it; GEMINI.md is a fallback.",
    ),
    "antigravity": AgentPlan(
        name="antigravity",
        display_name="Antigravity",
        targets=(
            "~/.gemini/GEMINI.md",
            "AGENTS.md",
        ),
        notes="Antigravity reads GEMINI.md and AGENTS.md; verify your installed version.",
    ),
}


def available_agents() -> list[str]:
    """Return supported agent identifiers in stable order."""
    return list(AGENT_PLANS)


def plan_installation(agent: str) -> AgentPlan:
    """Return the dry-run plan for one agent."""
    key = agent.strip().lower()
    if key not in AGENT_PLANS:
        choices = ", ".join(available_agents())
        raise KeyError(f"unknown agent {agent!r}; choose one of: {choices}")
    return AGENT_PLANS[key]


def format_plan(plan: AgentPlan) -> str:
    """Render a plan for terminal output."""
    lines = [
        f"Agent: {plan.display_name} ({plan.name})",
        "Mode: dry run - no files will be modified.",
        "Targets:",
    ]
    lines.extend(f"  - {target}" for target in plan.targets)
    if plan.notes:
        lines.append(f"Note: {plan.notes}")
    return "\n".join(lines)
