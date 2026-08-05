# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for issue operations from this checkout; it resolves the repository from `origin`.

## Conventions

- Create: `gh issue create --title "..." --body "..."`.
- Read: `gh issue view <number> --comments`.
- List: `gh issue list --state open` with the labels and fields required by the task.
- Comment, label, and close through `gh issue comment`, `gh issue edit`, and `gh issue close`.

## Pull requests as a triage surface

**PRs as a request surface: no.**

## Publishing and wayfinding

When an engineering skill says to publish to the issue tracker, create a GitHub issue. `/wayfinder` uses one map issue and GitHub child issues, with native dependencies where available.
