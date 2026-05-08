# Frontend-Backend Branching & Synchronization Strategy

This document outlines the branching strategy and workflow for maintaining synchronization between the **tinboker-platform/frontend** (Frontend) and **tinboker-platform/backend** (Backend) repositories.

## 1. Core Branches

Both repositories maintain two permanent branches:

| Branch | Environment | Purpose | Access |
| :--- | :--- | :--- | :--- |
| **`main`** | **Production** | Stable, deployable code. Reflects the live application. | Protected (PR only) |
| **`develop`** | **Staging / Beta** | Integration branch for new features. Deployed to Staging environment for testing. | Protected (PR only) |

### Environment Alignment
*   **Frontend `develop`** consumes **Backend `develop`** API.
*   **Frontend `main`** consumes **Backend `main`** API.

---

## 2. Development Workflow (Gitflow)

We use a variation of Gitflow to manage features and releases safely.

### A. Feature Development
*   **Branch:** `feature/feature-name` (e.g., `feature/spotify-integration`)
*   **Source:** `develop`
*   **Process:**
    1.  Create `feature/xxx` in **Backend** first (if API changes are needed).
    2.  Implement API changes and update `openapi.yaml`.
    3.  Create `feature/xxx` in **Frontend**.
    4.  Sync `openapi.yaml` from Backend `feature/xxx` to Frontend `feature/xxx`.
    5.  Implement UI/Logic using new API.
    6.  **Merge:** Backend PR to `develop` -> Frontend PR to `develop`.

### B. Release Candidate (Migration)
When `develop` contains a set of features ready for production:

*   **Branch:** `release/vX.X.X` (e.g., `release/v1.2.0`)
*   **Source:** `develop`
*   **Purpose:** Final testing, bug fixes, and version bumping. **No new features.**
*   **Process:**
    1.  Create `release/v1.2.0` in both repos.
    2.  Perform integration testing on Staging (pointing Frontend Release to Backend Release).
    3.  Fix bugs directly on `release/v1.2.0`.
    4.  **Merge:** Merge `release/v1.2.0` into **`main`** (deploy to Prod) AND back into **`develop`**.

### C. Hotfixes
For critical bugs in Production:

*   **Branch:** `hotfix/bug-description`
*   **Source:** `main`
*   **Process:**
    1.  Fix bug on `hotfix` branch.
    2.  Merge into **`main`** AND **`develop`**.

---

## 3. Synchronization Methodology

To ensure the Frontend never breaks due to Backend API changes:

### Phase 1: Backward Compatible Backend
*   Backend updates on `develop` should be **backward compatible** whenever possible (e.g., add new fields, don't remove old ones immediately).
*   If a breaking change is required, coordinate the merge timing.

### Phase 2: API Contract Sync
1.  Backend developer updates `src/schemas/openapi.yaml` (automatically generated or manual).
2.  Backend `develop` is updated.
3.  Frontend developer copies `openapi.yaml` to `src/schemas/openapi.yaml` in Frontend repo.
4.  Frontend types/client are updated (if auto-generated) or code is adjusted.

### Phase 3: Safe Migration (The "Intermediate" Branch)
If a major API refactor is risky, use an **Integration Branch**:

1.  **Backend:** Create `integration/v2-api`.
2.  **Frontend:** Create `integration/v2-ui`.
3.  Point Frontend `integration` to Backend `integration` (via env var `VITE_API_BASE_URL`).
4.  Test thoroughly.
5.  Merge both to their respective `develop` branches simultaneously.

---

## 4. Branching Diagram

```mermaid
gitGraph
   commit id: "Initial"
   branch develop
   checkout develop
   commit id: "Init Develop"
   
   branch feature/api-update
   checkout feature/api-update
   commit id: "Backend: Add Tags"
   checkout develop
   merge feature/api-update id: "Merge Backend"
   
   branch feature/ui-tags
   checkout feature/ui-tags
   commit id: "Frontend: Show Tags"
   checkout develop
   merge feature/ui-tags id: "Merge Frontend"
   
   branch release/v1.0
   checkout release/v1.0
   commit id: "Bump Version"
   checkout main
   merge release/v1.0 tag: "v1.0.0"
   checkout develop
   merge release/v1.0
```

## 5. Checklist for Merging

Before merging `develop` to `main`:

*   [ ] **Backend:** Is the API fully deployed and stable on Staging?
*   [ ] **Frontend:** Does the UI handle all edge cases (loading, error, empty states) from the Staging API?
*   [ ] **Sync:** Is `openapi.yaml` in Frontend identical to Backend `main` candidate?
*   [ ] **Smoke Test:** Have critical paths (Stock Detail, News Feed, Podcast Player) been verified?

