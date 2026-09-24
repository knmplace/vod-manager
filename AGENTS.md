# Repository operating rules

## Upstream pull requests

The `upstream-pr-hygiene` skill is mandatory for every upstream PR task in this repository. A PR must be clean and independently reviewable:

- branch from current upstream `main`;
- contain only the requested addition or fix;
- contain no previous PR commits, fork `main` history, changelog/bead/deployment files, screenshots, or unrelated changes;
- include a complete description and validation results;
- pass a preflight comparison of base/head repositories, commit list, changed-file list, and PR body before opening.

If a requested change depends on an unmerged upstream PR and cannot be isolated against upstream `main`, do not open a stacked or misleading PR. Wait for the dependency or obtain an explicit user decision to use a different integration strategy.
