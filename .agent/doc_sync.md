# Doc Sync Rules

After every code change, the agent must assess and update docs.

## What triggers a doc update

| Change type | Docs to update |
|---|---|
| New endpoint or function | `docs/API.md`, `README.md` |
| Architecture change | `docs/ARCHITECTURE.md` |
| Config/env var added | `README.md` (setup section) |
| Bug fix | `CHANGELOG.md`, optionally `docs/KNOWN_ISSUES.md` |
| New skill added | `.agents/skills/README.md` |
| Dependency added/removed | `README.md` (requirements section) |

## Update style
- Keep docs in sync with code — never leave a doc describing old behavior
- Use past tense in changelog: "Fixed", "Added", "Removed"
- One-line summary per change; link to issue ID from `issue_log.md`

## Changelog format (Keep a Changelog)
```
## [Unreleased]
### Fixed
- ISSUE-001: Fixed auth token expiry not being refreshed — backend-api-orchestration
### Added
- ...
```