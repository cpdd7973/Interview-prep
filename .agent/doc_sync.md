# Doc Sync Rules

After every code change, the agent must assess and update docs.

## What triggers a doc update

| Change type | Docs to update |
|---|---|
| New endpoint or function | `README.md` (API section) |
| Architecture change | `README.md` (Architecture section) |
| Config/env var added | `README.md` (setup section) |
| Bug fix | `CHANGELOG.md` |
| New skill added | Update `.agent/skill_router.md` routing table |
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