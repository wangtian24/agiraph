# Agiraph v2 — Competitive Landscape & Positioning

**Date:** 2026-02-09

---

## 1. Top 10 Competitors

| # | Framework | Stars | Momentum | Developer Sentiment |
|---|-----------|-------|----------|---------------------|
| 1 | **AutoGen** (Microsoft) | 54.4k | Declining — maintenance mode, pivoting to MS Agent Framework | Pioneered multi-agent but v0.2→v0.4 rewrite fractured community |
| 2 | **CrewAI** | 43.5k | Growing — 1M/mo downloads, shipping A2A support | Lowest learning curve, role metaphor. Power users hit ceilings |
| 3 | **Agno** (fka Phidata) | 37.5k | Surging — doubled in one year | "Just works." Fast, batteries-included. 100+ toolkits |
| 4 | **smolagents** (HuggingFace) | 25k | Growing — ~1000 lines core, agents write Python not JSON | Unix-philosophy darling. Anti-complexity bet |
| 5 | **LangGraph** (LangChain) | 24.4k | Growing — 4.2M/mo downloads, v1.0 stable | Enterprise incumbent. Powerful but "over-abstracted" reputation |
| 6 | **Mastra** | 20.9k | Surging — 1.5k→20.9k in 4 months, YC-backed | TypeScript-native. JS/TS crowd's answer to Python agent frameworks |
| 7 | **OpenAI Agents SDK** | 18.8k | Growing — weekly releases, expanding into AgentKit/Frontier | Clean design. Vendor coupling concerns despite "agnostic" claims |
| 8 | **CAMEL-AI** | 16k | Flat — research/academic focus | Respected in research. Not competing for production |
| 9 | **Google ADK** | 15.6k | Growing fast — multi-language (Py/TS/Java/Go) | Early but Google-backed. Developers wary of abandonment history |
| 10 | **PydanticAI** | 14.7k | Growing — 15M+ downloads, "Production/Stable" | "FastAPI feeling." Type-safe, boring-in-a-good-way infrastructure |

**Also notable:** Agency Swarm (3.9k, niche YouTube community), Atomic Agents (tiny but Unix-philosophy), Claude Agent SDK (4.7k, powers Claude Code).

---

## 2. Community Meta-Narrative

Three camps are forming in the developer community:

**"We need a Rails for agents"** — Convention over configuration. Developers want to describe a problem and get a working system without answering 50 architecture questions. Bryan Logue's "Agents Done Right" essay resonated widely.

**"Frameworks are the problem"** — If LLMs can generate code, why adopt someone else's opinionated architecture? Minority view but loud.

**"Unix philosophy or bust"** — Small composable tools, not monoliths. smolagents, Atomic Agents, and the arXiv paper "From 'Everything is a File' to 'Files Are All You Need'" represent this camp. MCP and A2A protocols (now at Linux Foundation) are the closest standards.

**Framework fatigue is real.** Gartner projects 40%+ of enterprise AI apps will have agentic components by end of 2026, but also 40%+ of early agentic projects will be abandoned due to poor architecture. The market is growing. The tooling is not mature. Winners will solve hard problems (context management, doom loops, reliability), not ship more wrappers.

---

## 3. Where Agiraph v2 Fits

### What nobody else does well (our gap)

| Differentiator | Closest competitor | Why we're different |
|---|---|---|
| **Role-based autonomy with adaptive re-planning** | CrewAI (roles but task-oriented) | Our coordinator re-plans between stages. Roles self-direct, not prescribed steps |
| **Two node types (API + Agentic)** | Nobody | Mix cheap API models with Claude Code / full agents in one team. Nobody supports this |
| **Filesystem-based shared workspace** | Nobody (all use in-memory state) | Files as truth. Debuggable. Future-proof for containers |
| **Stage-driven reconvene with collaboration contract** | LangGraph (checkpointing for recovery) | Ours is for coordination, not persistence |
| **"Describe a problem, get a team" one-liner** | CrewAI (close but manual setup) | Auto team assembly from a problem description |

### Where we learn from others

| Lesson | Who teaches it | Application |
|---|---|---|
| Simplicity wins adoption | smolagents (1000 lines), Agno ("just works") | Our `team()` one-liner. Small codebase. |
| Role metaphor resonates | CrewAI (43.5k stars on role concept alone) | Our named roles with human names |
| Model freedom is table stakes | Everyone except OpenAI SDK and Claude SDK | Support all providers from day one |
| Type-safety matters | PydanticAI | Use Pydantic for our data structures |
| Don't over-abstract | LangGraph backlash, smolagents philosophy | Functions, not class hierarchies. No plugin systems. |

### Our positioning

**Tagline:** "Describe a problem. Get a team."

**Against each competitor:**

| vs. | Why someone picks us |
|---|---|
| CrewAI | Adaptive re-planning. Agentic nodes. True autonomy, not task scripts |
| LangGraph | Dramatically simpler. No graph compilation. Problem → team → result |
| AutoGen | We're alive. They're in maintenance mode |
| smolagents | We're multi-agent with coordination. They're single-agent with hierarchy |
| Agno | We're collaborative team, not independent agents. Workspace sharing, messages |
| OpenAI SDK | Model-agnostic. Not locked to one provider |

---

## 4. Design Principles (Refined)

Based on competitive analysis:

1. **One line to start, thirty lines for full control.** The `team()` function is the front door. Everything else is progressive disclosure.
2. **Unix philosophy.** Small files, small functions, no inheritance. The entire codebase should be readable in 30 minutes.
3. **Files are the interface.** Shared workspace on disk. Message logs on disk. Everything inspectable without special tools.
4. **Model freedom.** Any provider with an API key in `.env`. No provider-specific code in the core.
5. **Two node types.** API nodes (harness runs the loop) and Agentic nodes (external agent runs itself). Same coordination interface.
