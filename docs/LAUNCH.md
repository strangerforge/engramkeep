# Launch playbook

This is the plan for the public launch of Engramkeep 0.5.2. It assumes the
repository is `github.com/strangerforge/engramkeep` and the package is published
on PyPI as `engramkeep`.

The goal of launch week is not a spike in stars. It is a first group of users
who install the tool, hit a real problem, and tell us what is missing.

## Positioning

**One line:** Your AI agents forget. Your memory shouldn't.

**Paragraph:** Engramkeep is local-first, Markdown-native memory for AI coding
agents. It stores project decisions and resolved fixes as plain files, installs
the protocol into ten agents with one backed-up command, and runs on the Python
standard library alone. No account, no cloud, no vector database.

**Who it is for:**

- Developers who use two or more coding agents and keep repeating context.
- People who want memory they can read, diff, and back up.
- Teams that cannot send source code or decisions to a hosted memory service.

**Who it is not for:**

- Teams looking for a hosted memory API with semantic retrieval.
- Anyone who wants automatic transcript scraping without reviewing what is
  stored.
- Large corpora that genuinely need embeddings.

**Proof points:**

- 254 tests, 85% coverage, CI on Linux, macOS, and Windows.
- 95.6% top-1 and 100% top-3 on a reproducible 45-query EN/TR benchmark.
- 100% top-1 for Turkish queries against English entries.
- Ten supported agents, managed blocks, backups, and reversible uninstall.
- Zero runtime dependencies.

Do not claim semantic search, perfect recall, or native integrations that have
not been tested. The benchmark page is the honest answer to "how good is it?".

## Assets

| Asset | Path | Use |
| --- | --- | --- |
| Dashboard screenshot | `assets/dashboard.png` | README, GitHub social preview, posts |
| Demo GIF | `assets/demo.gif` | README, Mastodon/X, dev.to |
| Benchmark | `docs/BENCHMARK.md` | Comments asking about recall quality |
| Installer docs | README section | Comments asking about agent setup |
| Comparison table | README section | Comments asking "why not Mem0?" |

Record a 60–90 second screen capture before launch: `pipx install`, `init`,
`remember`, `fixes`, `install --apply`, `dashboard`. Keep it unedited except for
speed. A terminal recording is more convincing than a polished promo.

## Repository settings

- Description: `Local-first, Markdown-native memory for AI coding agents. Zero runtime dependencies.`
- Website: the PyPI page or the README.
- Topics: `ai`, `agents`, `memory`, `mcp`, `markdown`, `local-first`, `python`, `cli`, `developer-tools`.
- Social preview: `assets/dashboard.png`.
- Enable Discussions. Pin a "Show your setup" thread.
- Labels: `good first issue`, `bug`, `enhancement`, `docs`, `security`, `question`.
- Security: private vulnerability reporting on, per `SECURITY.md`.
- Branch protection on `main`: require CI, require a pull request review for
  outside contributors, no force pushes.

## Launch sequence

### Day -7 to Day -1

- Publish 0.5.2 to PyPI through the release workflow.
- Verify a clean install in a fresh environment on Windows, macOS, and Linux.
- Create the `good first issue` issues from
  [GOOD_FIRST_ISSUES.md](GOOD_FIRST_ISSUES.md).
- Prepare the demo recording and three screenshots.
- Write the Show HN and Reddit drafts below and have one person outside the
  project read them for clarity.
- Do not ask for upvotes anywhere. It backfires and violates most community
  rules.

### Day 1 — Show HN

Post between 08:00 and 10:00 UTC on a weekday. Title:

> Show HN: Engramkeep – local-first Markdown memory for AI coding agents

Body:

> I use more than one coding agent, and every one of them starts from zero.
> The usual fixes are a hosted memory service or a vector database, and both
> ask me to send project context somewhere else and add a stack I cannot audit.
>
> Engramkeep keeps memory in plain Markdown on my machine. A card is a file I
> can open, diff, and back up. Resolved errors go into a troubleshooting
> registry, so the same build failure is not debugged twice. One command writes
> a managed, backed-up block into ten agent configs, and one command removes it.
>
> It runs on the Python standard library. No account, no telemetry, no network
> calls in the core. The repo includes a reproducible benchmark: 45 English and
> Turkish queries over synthetic fixes, 95.6% top-1, 100% top-3. It is lexical,
> not semantic, and the benchmark page says so.
>
> I would especially like feedback on the installer and on what is missing
> before the storage format is frozen.

Reply to every substantive comment for the first six hours. Link the benchmark
when someone asks about recall. Link the installer section when someone asks
about a specific agent. Do not argue with "just use a vector DB"; explain the
trade-off and move on.

### Day 2 — Reddit

Post to `r/LocalLLaMA` and `r/selfhosted` with a title that states the benefit,
not the feature list:

> I built a local-first memory layer for coding agents that stores everything as Markdown

Adapt the body to each community. `r/LocalLLaMA` cares about local execution
and model-agnostic tools. `r/selfhosted` cares about data ownership, backups,
and the absence of a cloud dependency. Do not cross-post the identical text in
the same hour.

### Day 3 — Turkish communities

Post a Turkish write-up to dev.to and the relevant Turkish developer
communities. Lead with the local-first angle and the EN/TR search, and link
`README.tr.md`. Turkish queries hitting English entries at 100% top-1 is a
concrete result worth showing.

### Day 4 — MCP and agent communities

- OpenCode, Claude Code, Cursor, and Windsurf community forums: post a short
  "how to add persistent memory" guide, not a product announcement.
- MCP directories: submit the server with the stdio command and the read-only
  tool list.
- Awesome lists: open a pull request only where the list explicitly accepts
  memory or MCP tools. Follow each list's contribution rules.

### Day 5–7 — Follow-up

- Collect every question into `docs/FAQ.md` (create it during the week, not
  before).
- Open issues for every credible bug and label them.
- Thank the first outside contributors by name in the release notes, with their
  permission.
- Publish a short "launch learnings" post with install numbers only if you are
  comfortable sharing them. Never publish another person's data.

## Drafts

### Short post (Mastodon / X / LinkedIn)

> Your agents forget. Your memory shouldn't.
>
> Engramkeep is local-first, Markdown-native memory for AI coding agents:
> - plain files you can read and diff
> - one backed-up install for ten agents
> - a troubleshooting registry for solved errors
> - zero runtime dependencies
>
> 254 tests. 85% coverage. 95.6% top-1 on a reproducible EN/TR benchmark.
>
> pipx install engramkeep
> github.com/strangerforge/engramkeep

### Comment reply: "Why not just use Mem0?"

> Mem0 is a good fit when you want a hosted or embedding-based memory service
> and you are fine sending context to it. Engramkeep optimises for a different
> constraint: the memory must stay a set of files I own, the tool must have no
> runtime dependencies, and every write must be reviewable with `git diff`.
> That trades semantic recall for auditability and portability. The benchmark
> in the repo shows what the lexical approach does and does not find.

### Comment reply: "Does it work with <agent>?"

> The installer supports OpenCode, Claude Code, OpenAI Codex, Cursor, Windsurf,
> Gemini CLI, Antigravity, GitHub Copilot, Cline, and Roo Code. Run
> `engramkeep install --list` to see the exact target paths on your platform,
> then `engramkeep install --agent <id>` for a dry run. If your agent reads
> `AGENTS.md` or `SKILL.md`, the templates work even when there is no dedicated
> installer entry. Tell me which agent you use and I will add it if the target
> path is documented.

## What to measure

Track weekly, not hourly:

| Metric | Why |
| --- | --- |
| PyPI downloads | Actual installation, not just interest |
| GitHub stars | Discovery, weak signal |
| Issues opened by non-authors | Whether people use it enough to hit bugs |
| Installer failures | The riskiest part of the first-run experience |
| Benchmark regressions | Whether search changes help or hurt |
| Time to first successful `remember` | The real activation metric |

Do not optimize for stars. A repository with 300 stars and 30 real users is
healthier than 3,000 stars and no installs.

## After launch

- Keep the issue tracker tidy; close stale questions with a link to the docs.
- Cut a patch release for launch-week bugs within a few days.
- Write down the three most common misunderstandings and fix the README, not
  just the reply.
- Revisit the roadmap after two weeks of real usage. The next milestone is
  transcript import and schema migrations, not more launch posts.
