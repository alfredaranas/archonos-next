# ADR-003: archonos-next kernel-clean push state (2026-06-16)

## Status

**Accepted** (recorded for the next session)

## Context

Session 2026-06-15 → 2026-06-16 built the spec-compliant archonos-next
kernel on a clean `kernel-clean` branch (off `milestone-0-5-1-cli-kernel`),
delivering 9 atomic commits covering M0.5 through M6 plus tier-2 polish
(PDF import, .archonosignore, cron, scheduler, config, CI, FTS5 bugfix).

130/130 tests passing locally in ~8s. Zero runtime dependencies.

## What we tried (and what didn't)

The user asked to push the work to `github.com/alfredaranas/archonos-next`.
This WSL node has:

- No `gh` CLI
- No `~/.git-credentials` or `~/.netrc`
- No `credential.helper` configured
- No stored GitHub token
- The `archonos` MCP server (`yoda_exec`) lives on a different host with
  fleet-only credentials, NOT github.com

The `mcp_github_*` tools available in this session DO have working auth
(verified by reading `README.md` and listing the repo tree successfully),
but they:

- Cannot do `git push` (Contents API only, not the git protocol)
- Are rate-limited under user 54632841 (hit it after ~2 multi-file
  `push_files` calls totaling ~25 KB raw)
- Cannot `delete_branch` (no such MCP tool exposed)

## What got onto origin (partial, contaminated)

A `kernel-clean` branch was created from `main`. The first two `push_files`
calls landed successfully:

1. `7a7e4981` — top-level + .github + README + pyproject + .gitignore
2. `53578fa0` — `src/archonos/storage/` (3 files)

But because origin's `main` is the polluted `master` snapshot (with
`server.py`, `wiki.py`, `mobile.html`, `mock-ui-*.html`, `ui/`, `kb/`,
`knowledge-packs/`, `Dockerfile` — the 8,987 LOC of legacy work the
kernel-clean branch was designed to AVOID), the new `origin/kernel-clean`
branch is in a mixed state: my clean README + storage files + 9 KB of
content sitting on top of 8,987 LOC of legacy junk.

## What the user needs to do to land this cleanly

```bash
cd /home/alfredaranas/archonos-next

# 1. Delete the contaminated branch on origin (will prompt for creds)
git push origin :refs/heads/kernel-clean

# 2. Push the clean local branch (same command will work after auth)
git push -u origin kernel-clean
```

Both commands will fail with `could not read Username` on the first try.
The first command's failure prints the auth URL; the second command
succeeds once credentials are provided.

## What's NOT blocked

- Local `kernel-clean` branch: 9 atomic commits, 130/130 tests passing
- Stash `parked-master-1781599230`: the 9,000 LOC of `master` junk is
  safely stashed; can be applied on `master` branch only
- `/tmp/archonos-untracked/`: safety copy of untracked files from master
- The demo KB at `/tmp/archonos-demo/default/archonos.db` with 3
  imported arXiv/OpenAlex papers + 4 chunks
- All source files, tests, docs, CI config

## Decision

Stop trying to push via the GitHub MCP. Land locally. The user is moving
to a different project and will return to this repo with proper auth
(PAT, SSH key, or `gh` CLI installed) when they want to publish.

## Consequences

- Work is on a local branch, backed up only by the user's WSL disk
- The contaminated `origin/kernel-clean` is misleading; user should
  delete it on first auth-bearing session
- The 9-commit history is preserved exactly as built; no future
  rebase or squash needed

## Next steps for the next session

1. Auth: install `gh` CLI OR set up SSH key OR paste a PAT
2. Delete `origin/kernel-clean`
3. `git push -u origin kernel-clean` (preserves 9 atomic commits)
4. Open PR against `main` (or against a freshly cleaned default branch)
5. CI in `.github/workflows/test.yml` will run on the PR — validates
   the kernel on `ubuntu-latest × Python 3.11 + 3.12`
