# GitHub Actions Checks Setup for Interview Platform

## Quick Start

### Step 1: Create Workflow File
Copy the workflow file to your repo at this exact path:
```
.github/workflows/checks.yml
```

**On your machine:**
```bash
mkdir -p .github/workflows
cp github-checks-workflow.yml .github/workflows/checks.yml
```

### Step 2: Commit and Push
```bash
git add .github/workflows/checks.yml
git commit -m "feat: add GitHub Actions checks for CI/CD"
git push origin your-branch
```

### Step 3: Watch the Magic
Go to your PR → you'll see the checks running in real-time under the "Checks" tab.

---

## What Each Check Does

### Python Checks
1. **python-security**: Bandit (code vulnerabilities) + detect-secrets + pip-audit (CVEs)
2. **python-quality**: Black (formatting) + Ruff (linting) + Mypy (types)
3. **python-tests**: pytest with coverage reports

### Node.js / React Checks
1. **node-security**: npm audit + Snyk vulnerability scan
2. **node-quality**: ESLint + Prettier formatting
3. **node-tests**: npm test with coverage

### Pre-commit
Runs all pre-commit hooks (backup check)

---

## Customize for Your Project

### If you don't have pytest/npm scripts:

**For Python**, update your workflow:
```yaml
- name: Run tests
  run: |
    pytest tests/ --cov=app --cov-report=xml || true
```

**For Node.js**, if you don't have `npm test`:
```yaml
- name: Run tests
  run: |
    npm run build || true
```

### Disable checks you don't need yet:
Remove entire job blocks if you're not ready (e.g., remove `node-security` if you're not ready for Snyk).

### Required vs Optional:
- Mark security scans as `continue-on-error: true` initially, then make them strict
- Keep tests and linting strict (fail the PR)

---

## GitHub Settings: Block Merge on Failed Checks

After your first workflow runs:

1. Go to **Settings** → **Branches** → **Add rule**
2. Select your `main` or `dev` branch
3. Check: **Require status checks to pass before merging**
4. Select all the checks you want to enforce:
   - ✅ python-security
   - ✅ python-quality
   - ✅ python-tests
   - ✅ node-quality
   - ✅ node-tests
   - ✅ pre-commit

Now **no one can merge without passing these checks**. 🔒

---

## Optional: Add Badge to README

Show off your passing checks:
```markdown
![Checks](https://github.com/YOUR_USERNAME/YOUR_REPO/workflows/Code%20Quality%20%26%20Security%20Checks/badge.svg)
```

---

## Troubleshooting

### "No checks for this commit"
- Make sure `.github/workflows/checks.yml` is committed and pushed
- Give GitHub ~30 seconds to register the workflow
- Go to **Actions** tab to see if workflow is registered

### "Workflow is skipped"
- Check branch protection rules — workflow might need read permissions
- If forked repo: enable Actions in repo Settings

### Checks fail locally but pass in Actions?
- Python version mismatch: Update to 3.11 everywhere
- Node version mismatch: Update to 18 LTS everywhere
- Missing dependencies: Run `pip install -r requirements.txt` or `npm ci`

---

## Next Steps

1. **Add pre-commit hooks locally** (from earlier guide) — they'll match your CI checks
2. **Update `pyproject.toml` and `.eslintrc.json`** with your linting rules
3. **Generate `.secrets.baseline`** before first run: `detect-secrets scan > .secrets.baseline`
4. **Set branch protection rules** so PRs can't merge without passing checks

Questions? DM me!
