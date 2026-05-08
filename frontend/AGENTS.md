# Agent Instructions for tinboker-platform/frontend

These instructions are for AI assistants working on the frontend codebase.

## PR Merge Rules

**NEVER merge PRs without explicit user permission.**

When working on feature branches:
1. Make changes and commit to the feature branch
2. Push to GitHub and create/update PR
3. **Wait for user approval before merging**
4. Do NOT directly push to `develop` or `main` branches

### Allowed actions without explicit permission:
- Creating feature branches
- Pushing commits to feature branches
- Creating PRs from feature branches
- Updating existing PRs

### Actions requiring explicit user permission:
- Merging PRs to `develop`
- Merging PRs to `main`
- Force pushing to any branch
- Deleting branches

## Git Workflow

- Feature branches: `feat/<feature-name>` from `develop`
- Bug fixes: `fix/<bug-name>` from `develop`
- Hotfixes: `hotfix/<issue>` from `main`
- PRs require Cloudflare build check to pass before merge

## Deployment

Frontend is deployed via Cloudflare Pages:
- `develop` branch → `dev.tinboker.com`
- `main` branch → `tinboker.com`
- Preview deployments → `*.tinboker-platform.pages.dev`

Each environment uses its corresponding backend API:
- `dev.tinboker.com` → `dev-api.tinboker.com`
- `staging.tinboker.com` → `staging-api.tinboker.com`
- `tinboker.com` → `api.tinboker.com`
