# Namespace Conflict Fix for Content-Builder

## Problem

**Namespace Conflict**: The Content-Builder package uses `src` as its package name, which conflicts with the local project's `src/` directory.

### Current Situation

1. **Local Project Structure**:
   ```
   Podcast-Downloader/
   ├── src/
   │   ├── summarize_content.py
   │   ├── upload_to_firebase.py
   │   └── ... (other local modules)
   ```

2. **Installed Package Structure**:
   ```
   .venv/lib/python3.10/site-packages/
   └── src/
       ├── api.py
       ├── agents/
       ├── models/
       └── ... (Content-Builder package)
   ```

3. **Import Issue**:
   ```python
   from src.api import analyze_transcript  # ❌ Fails
   # Python finds local src/ directory first, can't find src.api
   ```

### Why It Fails

When Python imports `from src.api`, it searches `sys.path` in order:
1. Current directory (`.`) - finds local `src/` directory
2. Site-packages - never reached because local `src/` is found first

Since the local `src/` doesn't have `api.py`, the import fails.

---

## Solution

**Rename the package in Content-Builder repository** to avoid the conflict.

### Recommended Package Name

Use `content_builder` or `podcast_analysis_agents` (matches the package name in `pyproject.toml`).

### Changes Needed in Content-Builder Repository

#### 1. Rename Package Directory

**Before**:
```
Content-Builder/
└── src/
    ├── __init__.py
    ├── api.py
    ├── agents/
    └── ...
```

**After**:
```
Content-Builder/
└── content_builder/  (or podcast_analysis_agents/)
    ├── __init__.py
    ├── api.py
    ├── agents/
    └── ...
```

#### 2. Update `pyproject.toml`

Update the package configuration:

```toml
[project]
name = "podcast-analysis-agents"  # Keep this as-is

[tool.setuptools]
packages = ["content_builder"]  # Change from ["src"]

[tool.setuptools.package-data]
"*" = ["configs/*.yaml"]  # Already fixed
```

#### 3. Update `src/api.py` Imports

Update all internal imports in the package:

**Before**:
```python
from src.agents.orchestrator import Orchestrator
from src.models.output import MarkdownReport
```

**After**:
```python
from content_builder.agents.orchestrator import Orchestrator
from content_builder.models.output import MarkdownReport
```

#### 4. Update Documentation

Update the import example in documentation:

**Before**:
```python
from src.api import analyze_transcript
```

**After**:
```python
from content_builder.api import analyze_transcript
```

---

## Alternative Solution (If Renaming Is Not Possible)

If renaming the package is not feasible, we can work around it in this project by:

1. Using `importlib` to load from a specific path
2. Temporarily modifying `sys.path` during import
3. Using a different import mechanism

However, **renaming the package is the cleanest solution** and prevents conflicts with other projects that might also use `src/` as a directory name.

---

## After Fix

Once the package is renamed, the import will work cleanly:

```python
from content_builder.api import analyze_transcript

# No namespace conflict!
result = analyze_transcript(
    transcript=transcript_text,
    source="My Podcast",
    episode_title="Episode 1"
)
```

---

## Summary

**Issue**: Package name `src` conflicts with local project's `src/` directory  
**Fix**: Rename package to `content_builder` (or `podcast_analysis_agents`)  
**Files to Update**:
- Rename `src/` → `content_builder/` directory
- Update `pyproject.toml` packages configuration
- Update all internal imports (`from src.` → `from content_builder.`)
- Update `src/api.py` → `content_builder/api.py` location
- Update documentation examples

