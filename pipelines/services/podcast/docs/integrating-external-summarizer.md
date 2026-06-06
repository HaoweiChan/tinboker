# Integrating External Summarizer from GitHub

This document outlines best practices for replacing the placeholder summarizer with an external implementation from a GitHub repository.

## Current Interface

The `SummarizeService.generate_summary_from_text()` method expects:

**Input:**
- `transcript_text: str` - The transcript text content

**Output:**
- `Dict` with keys:
  - `summary_text: str` - Markdown summary text
  - `svg_content: str` - SVG XML string for visualization
  - `related_tickers: List[str]` - List of ticker symbols

## Best Practices

### 1. Install as a Git Dependency

#### ⭐ **Option A: Install directly from GitHub (BEST - Recommended)**

**Why this is best:**
- ✅ **Simple**: Just add one line to `requirements.txt`
- ✅ **Version Control**: Pin to specific version/tag for stability
- ✅ **Standard Practice**: Most Python projects use this approach
- ✅ **Easy Updates**: Change version in `requirements.txt` and reinstall
- ✅ **No Repo Clutter**: Doesn't add files to your repository
- ✅ **Works Everywhere**: Local dev, Docker, CI/CD, cloud deployments

**Implementation:**

Add to `requirements.txt`:
```txt
# External summarizer from GitHub
# Pin to specific version/tag for stability
git+https://github.com/username/repo-name.git@v1.0.0#egg=package-name
```

Or for a specific branch:
```txt
git+https://github.com/username/repo-name.git@main#egg=package-name
```

Or for a specific commit (most stable):
```txt
git+https://github.com/username/repo-name.git@abc123def456#egg=package-name
```

**Install:**
```bash
pip install -r requirements.txt
```

#### Option B: Install as editable (Only for active development)

**When to use:** Only if you're actively developing/forking the external repo and need to make changes.

**Pros:**
- ✅ Changes to external repo are immediately available
- ✅ Good for debugging/fixing issues in external repo

**Cons:**
- ❌ Requires cloning the full repo
- ❌ More complex setup
- ❌ Not suitable for production
- ❌ Harder to version control

**Implementation:**
```bash
# Clone and install in editable mode
git clone https://github.com/username/repo-name.git external/summarizer
pip install -e external/summarizer
```

**Note:** Add `external/` to `.gitignore` if you don't want to commit it.

#### Option C: Use a Git submodule (Rarely needed)

**When to use:** Only if you need the full repository files (not just the package) and want to track specific commits.

**Pros:**
- ✅ Tracks specific commit of external repo
- ✅ Can access all files in external repo

**Cons:**
- ❌ More complex to manage
- ❌ Requires git submodule commands
- ❌ Can be confusing for team members
- ❌ Usually unnecessary for Python packages

**Implementation:**
```bash
git submodule add https://github.com/username/repo-name.git external/summarizer
git submodule update --init --recursive
```

**Then install:**
```bash
pip install -e external/summarizer
```

### 2. Update requirements.txt (Using Option A - Recommended)

Add the dependency to your `requirements.txt`:

```txt
# Existing dependencies
firebase-admin>=6.0.0
google-cloud-storage>=2.10.0
# ... other dependencies ...

# External summarizer
git+https://github.com/username/summarizer-repo.git@main#egg=summarizer-package
```

### 3. Implement Adapter Pattern

Create an adapter to maintain the same interface while using the external library:

**File: `src/summarize_content.py`**

```python
#!/usr/bin/env python3
"""
Summary Content Generator

This module provides functionality to generate summaries, SVG images, and extract
related tickers from podcast transcripts.
"""

import random
from pathlib import Path
from typing import Dict, List, Optional

# Try to import external summarizer, fallback to placeholder if not available
try:
    from external_summarizer import generate_summary as external_generate_summary
    EXTERNAL_SUMMARIZER_AVAILABLE = True
except ImportError:
    EXTERNAL_SUMMARIZER_AVAILABLE = False
    print("⚠ Warning: External summarizer not available, using placeholder")


class SummarizeService:
    """Service for generating summaries, SVG images, and tickers from transcripts."""
    
    def __init__(self, use_external: bool = True):
        """
        Initialize the summarizer service.
        
        Args:
            use_external: If True, use external summarizer if available, else use placeholder
        """
        self.use_external = use_external and EXTERNAL_SUMMARIZER_AVAILABLE
    
    def generate_summary_from_text(self, transcript_text: str) -> Dict:
        """
        Generate summary, SVG, and tickers from transcript text.
        
        Args:
            transcript_text: Transcript text content (string)
            
        Returns:
            Dictionary with:
                - summary_text: Summary text (markdown)
                - svg_content: SVG XML string
                - related_tickers: List of ticker symbols
        """
        if self.use_external:
            try:
                # Call external summarizer
                result = external_generate_summary(transcript_text)
                
                # Adapt external result to our expected format
                return self._adapt_external_result(result, transcript_text)
            except Exception as e:
                print(f"⚠ Error using external summarizer: {e}")
                print("  Falling back to placeholder...")
                return self._generate_placeholder(transcript_text)
        else:
            return self._generate_placeholder(transcript_text)
    
    def _adapt_external_result(self, external_result: Dict, transcript_text: str) -> Dict:
        """
        Adapt external summarizer result to our expected format.
        
        Args:
            external_result: Result from external summarizer (format may vary)
            transcript_text: Original transcript text
            
        Returns:
            Dictionary in our expected format
        """
        # Adapt based on external library's output format
        # Example adaptations:
        
        # If external returns different keys
        summary_text = external_result.get('summary', external_result.get('text', ''))
        
        # If external doesn't provide SVG, generate one from summary
        svg_content = external_result.get('svg', self._generate_svg_from_summary(summary_text))
        
        # If external doesn't provide tickers, extract them
        related_tickers = external_result.get('tickers', external_result.get('related_tickers', []))
        if not related_tickers:
            related_tickers = self._extract_tickers_from_summary(summary_text)
        
        return {
            'summary_text': summary_text,
            'svg_content': svg_content,
            'related_tickers': related_tickers
        }
    
    def _generate_placeholder(self, transcript_text: str) -> Dict:
        """Generate placeholder summary (fallback)."""
        transcript_length = len(transcript_text)
        summary_text = self._generate_placeholder_summary(transcript_length)
        svg_content = self._generate_placeholder_svg()
        num_tickers = random.randint(3, 7)
        related_tickers = random.sample(self.PLACEHOLDER_TICKERS, min(num_tickers, len(self.PLACEHOLDER_TICKERS)))
        
        return {
            'summary_text': summary_text,
            'svg_content': svg_content,
            'related_tickers': related_tickers
        }
    
    # ... rest of placeholder methods ...
```

### 4. Environment Variable Configuration

Add an environment variable to control which summarizer to use:

**`.env` file:**
```bash
# Summarizer configuration
USE_EXTERNAL_SUMMARIZER=true  # Set to false to use placeholder
SUMMARIZER_MODEL=default      # Model name for external summarizer (if applicable)
```

**Update code:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

class SummarizeService:
    def __init__(self, use_external: Optional[bool] = None):
        if use_external is None:
            use_external = os.getenv("USE_EXTERNAL_SUMMARIZER", "true").lower() == "true"
        self.use_external = use_external and EXTERNAL_SUMMARIZER_AVAILABLE
```

### 5. Error Handling

Always wrap external calls in try-except blocks:

```python
try:
    result = external_summarizer_function(transcript_text)
except ImportError:
    # Library not installed
    print("⚠ External summarizer not available")
    return self._generate_placeholder(transcript_text)
except Exception as e:
    # Runtime error
    print(f"⚠ Error in external summarizer: {e}")
    return self._generate_placeholder(transcript_text)
```

### 6. Version Pinning

Pin to a specific version/tag for stability:

```txt
# In requirements.txt
git+https://github.com/username/repo-name.git@v1.2.3#egg=package-name
```

Or use a commit hash:
```txt
git+https://github.com/username/repo-name.git@abc123def#egg=package-name
```

### 7. Alternative: Direct Function Import

If the GitHub repo exports a simple function:

```python
# Option 1: Import from installed package
from summarizer_package import generate_summary

# Option 2: Import from specific module
from summarizer_package.summarize import generate_summary

# Option 3: Import with alias
from summarizer_package import generate_summary as external_summarize
```

### 8. Testing Both Implementations

Add tests to ensure both work:

```python
# tests/test_summarize_content.py

def test_placeholder_summarizer():
    service = SummarizeService(use_external=False)
    result = service.generate_summary_from_text("Test transcript")
    assert 'summary_text' in result
    assert 'svg_content' in result
    assert 'related_tickers' in result

def test_external_summarizer():
    if EXTERNAL_SUMMARIZER_AVAILABLE:
        service = SummarizeService(use_external=True)
        result = service.generate_summary_from_text("Test transcript")
        assert 'summary_text' in result
        assert 'svg_content' in result
        assert 'related_tickers' in result
```

## Example Implementation

Here's a complete example of integrating an external summarizer:

```python
# src/summarize_content.py

import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

# Try to import external summarizer
try:
    # Adjust import based on actual package structure
    from external_summarizer import summarize_transcript, extract_tickers, generate_visualization
    EXTERNAL_AVAILABLE = True
except ImportError:
    EXTERNAL_AVAILABLE = False

class SummarizeService:
    def __init__(self, use_external: Optional[bool] = None):
        if use_external is None:
            use_external = os.getenv("USE_EXTERNAL_SUMMARIZER", "true").lower() == "true"
        self.use_external = use_external and EXTERNAL_AVAILABLE
    
    def generate_summary_from_text(self, transcript_text: str) -> Dict:
        if self.use_external:
            return self._generate_with_external(transcript_text)
        else:
            return self._generate_placeholder(transcript_text)
    
    def _generate_with_external(self, transcript_text: str) -> Dict:
        try:
            # Call external functions
            summary_text = summarize_transcript(transcript_text)
            related_tickers = extract_tickers(transcript_text)
            svg_content = generate_visualization(summary_text)
            
            return {
                'summary_text': summary_text,
                'svg_content': svg_content,
                'related_tickers': related_tickers
            }
        except Exception as e:
            print(f"⚠ External summarizer error: {e}, using placeholder")
            return self._generate_placeholder(transcript_text)
    
    # ... placeholder methods ...
```

## Quick Start Guide (Recommended Approach)

### Step-by-Step: Install + Merge .env = Ready to Run! ✅

**Yes, that's exactly right!** Follow these steps:

#### Step 1: Install the External Repo

Add to `requirements.txt`:
```txt
# External summarizer
git+https://github.com/username/repo-name.git@v1.0.0#egg=package-name
```

Install it:
```bash
pip install -r requirements.txt
```

#### Step 2: Merge Environment Variables

Check what environment variables the external repo needs (usually in their README or `.env.example`), then add them to **your** `.env` file:

**Your `.env` file:**
```bash
# Your existing variables
GCP_CREDENTIALS_JSON=...
GCS_BUCKET_NAME=...
GCS_BASE_PATH=podcasts

# External summarizer variables (from their requirements)
OPENAI_API_KEY=your-openai-api-key-here
SUMMARIZER_MODEL=gpt-4
SUMMARIZER_TEMPERATURE=0.7
# ... any other variables the external repo needs
```

#### Step 3: Update Your Code (Optional)

If the external library's interface doesn't match exactly, create a simple adapter:

**File: `src/summarize_content.py`**
```python
try:
    from external_package import summarize_function
    EXTERNAL_AVAILABLE = True
except ImportError:
    EXTERNAL_AVAILABLE = False

class SummarizeService:
    def generate_summary_from_text(self, transcript_text: str) -> Dict:
        if EXTERNAL_AVAILABLE:
            try:
                # Call external function
                result = summarize_function(transcript_text)
                # Adapt to your expected format
                return {
                    'summary_text': result.get('summary', ''),
                    'svg_content': result.get('svg', self._generate_placeholder_svg()),
                    'related_tickers': result.get('tickers', [])
                }
            except Exception as e:
                print(f"⚠ External summarizer error: {e}, using placeholder")
                return self._generate_placeholder(transcript_text)
        else:
            return self._generate_placeholder(transcript_text)
```

#### Step 4: Run!

That's it! Your pipeline will now use the external summarizer:

```bash
python main.py
```

### ✅ Summary

1. ✅ **Install** → Add to `requirements.txt` and run `pip install -r requirements.txt`
2. ✅ **Merge .env** → Add external repo's required variables to your `.env`
3. ✅ **Run** → It works! The external library will read from your `.env` automatically

**No additional configuration needed** - Python's `os.getenv()` will automatically read from your `.env` file (via `python-dotenv`), and the external library will use those values.

## Checklist

- [ ] Add GitHub dependency to `requirements.txt` (use Option A - direct install)
- [ ] Pin to specific version/tag for stability
- [ ] Install dependency: `pip install -r requirements.txt`
- [ ] Create adapter function to match expected interface
- [ ] Add error handling with fallback to placeholder
- [ ] Add environment variable to toggle between implementations
- [ ] Update tests to cover both implementations
- [ ] Document the external dependency in README
- [ ] Pin to specific version/tag for stability
- [ ] Test in both streaming and file-based modes

## Handling External Repo with .env Configuration

If the external GitHub repository requires its own `.env` file (e.g., for AI API keys, model configurations), here are best practices:

### ⭐ **RECOMMENDED: Option 1 - Merge Environment Variables**

**This is the best approach** because it's simple, maintainable, and follows standard practices.

### Option 1: Merge Environment Variables ⭐ **BEST CHOICE**

**Why this is the best approach:**
- ✅ **Simple**: Single `.env` file to manage
- ✅ **Standard Practice**: Most projects use one `.env` file
- ✅ **No Conflicts**: Your variables take precedence
- ✅ **Easy to Document**: One `.env.example` file
- ✅ **Version Control Safe**: `.env` is gitignored, `.env.example` is tracked
- ✅ **Works Everywhere**: Local dev, Docker, cloud deployments

**Implementation:**

Add the external repo's required environment variables to your own `.env` file:

**Your `.env` file:**
```bash
# Your existing variables
GCP_CREDENTIALS_JSON=...
GCS_BUCKET_NAME=...

# External summarizer configuration
OPENAI_API_KEY=your-openai-key          # If external uses OpenAI
ANTHROPIC_API_KEY=your-anthropic-key    # If external uses Claude
SUMMARIZER_MODEL=gpt-4                  # Model selection
SUMMARIZER_TEMPERATURE=0.7              # Model parameters
```

**Benefits:**
- Single source of truth for all configuration
- Easy to manage and version control (with `.env.example`)
- No conflicts between multiple `.env` files

### Option 2: Pass Configuration Programmatically (Good Alternative)

**When to use:** If the external library supports programmatic configuration and you want more control.

**Pros:**
- ✅ Explicit configuration in code
- ✅ Type-safe if using typed config objects
- ✅ Easy to test with mock configurations

**Cons:**
- ❌ Requires code changes if config changes
- ❌ Less flexible than environment variables
- ❌ May not work if external library only reads from `.env`

**Implementation:**

If the external library supports programmatic configuration, pass it directly:

```python
# src/summarize_content.py

import os
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from external_summarizer import Summarizer
    
    # Initialize with configuration from your .env
    external_summarizer = Summarizer(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("SUMMARIZER_MODEL", "gpt-4"),
        temperature=float(os.getenv("SUMMARIZER_TEMPERATURE", "0.7"))
    )
    EXTERNAL_AVAILABLE = True
except ImportError:
    EXTERNAL_AVAILABLE = False
    external_summarizer = None

class SummarizeService:
    def _generate_with_external(self, transcript_text: str) -> Dict:
        try:
            # Use pre-configured instance
            result = external_summarizer.summarize(transcript_text)
            return self._adapt_external_result(result, transcript_text)
        except Exception as e:
            print(f"⚠ External summarizer error: {e}")
            return self._generate_placeholder(transcript_text)
```

### Option 3: Load External .env Conditionally (Not Recommended)

**When to use:** Only if you absolutely cannot modify the external repo's `.env` structure.

**Pros:**
- ✅ Keeps external repo's structure intact

**Cons:**
- ❌ Multiple `.env` files to manage
- ❌ Confusing which file has which variables
- ❌ Harder to debug configuration issues
- ❌ Doesn't work well in containerized deployments

**Implementation:**

If the external repo requires its own `.env` file structure, load it conditionally:

```python
# src/summarize_content.py

import os
from pathlib import Path
from dotenv import load_dotenv, dotenv_values

# Load your main .env first
load_dotenv()

# Optionally load external .env if it exists
EXTERNAL_ENV_PATH = Path("external_summarizer/.env")
if EXTERNAL_ENV_PATH.exists():
    # Load external .env and merge with current environment
    external_env = dotenv_values(EXTERNAL_ENV_PATH)
    for key, value in external_env.items():
        if key not in os.environ:  # Don't override your existing vars
            os.environ[key] = value
    print("✓ Loaded external summarizer .env configuration")
```

### Option 4: Use Environment Variable Prefixes (Useful for Organization)

**When to use:** When you have many external dependencies and want to organize them clearly.

**Pros:**
- ✅ Clear organization of variables
- ✅ Avoids naming conflicts
- ✅ Easy to see which variables belong to which dependency

**Cons:**
- ❌ Requires mapping code to convert prefixed vars to expected names
- ❌ More verbose variable names

**Implementation:**

Use prefixes to organize variables and avoid conflicts:

**Your `.env` file:**
```bash
# Your app variables
GCP_CREDENTIALS_JSON=...
GCS_BUCKET_NAME=...

# External summarizer variables (with prefix)
EXTERNAL_SUMMARIZER_OPENAI_API_KEY=your-key
EXTERNAL_SUMMARIZER_MODEL=gpt-4
EXTERNAL_SUMMARIZER_TEMPERATURE=0.7
```

**Adapter code:**
```python
def _configure_external_summarizer():
    """Configure external summarizer from environment variables."""
    config = {
        'api_key': os.getenv("EXTERNAL_SUMMARIZER_OPENAI_API_KEY"),
        'model': os.getenv("EXTERNAL_SUMMARIZER_MODEL", "gpt-4"),
        'temperature': float(os.getenv("EXTERNAL_SUMMARIZER_TEMPERATURE", "0.7"))
    }
    
    # Map to external library's expected variable names
    if config['api_key']:
        os.environ['OPENAI_API_KEY'] = config['api_key']  # If external expects this
    
    return config
```

### Option 5: Configuration File Approach (Overkill for Most Cases)

**When to use:** For complex configurations with many nested settings or when you need configuration validation.

**Pros:**
- ✅ Structured configuration
- ✅ Can validate configuration
- ✅ Supports nested/complex configs

**Cons:**
- ❌ More complex than needed for simple cases
- ❌ Another file to manage
- ❌ Still need to load from environment variables anyway

**Implementation:**

Create a separate config file for external dependencies:

**`config/external_summarizer.json`:**
```json
{
  "api_key": "${OPENAI_API_KEY}",
  "model": "gpt-4",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**Load and use:**
```python
import json
from pathlib import Path

def load_external_config():
    config_path = Path("config/external_summarizer.json")
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
            # Replace ${VAR} with environment variables
            for key, value in config.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    config[key] = os.getenv(env_var, value)
            return config
    return {}
```

### Best Practice: Document Required Variables

Create a `.env.example` file documenting all required variables:

**`.env.example`:**
```bash
# Your application variables
GCP_CREDENTIALS_JSON=your-gcp-credentials-json
GCS_BUCKET_NAME=your-bucket-name
GCS_BASE_PATH=podcasts

# External Summarizer Configuration
# Get API key from: https://platform.openai.com/api-keys
OPENAI_API_KEY=your-openai-api-key
SUMMARIZER_MODEL=gpt-4
SUMMARIZER_TEMPERATURE=0.7
SUMMARIZER_MAX_TOKENS=2000

# Optional: External summarizer specific variables
# (Add any other variables required by the external library)
```

### Handling Multiple .env Files (Not Recommended)

If you must use separate `.env` files:

```python
# Load in priority order (your .env takes precedence)
load_dotenv(".env")  # Your main .env
load_dotenv("external/.env", override=False)  # External .env (won't override)
```

**⚠️ Warning:** This approach can be confusing and error-prone. Prefer merging into a single `.env` file.

### Example: Complete Integration with External .env Requirements

```python
# src/summarize_content.py

import os
from typing import Dict, Optional
from dotenv import load_dotenv

# Load your main .env
load_dotenv()

# Check if external summarizer is available
try:
    from external_summarizer import Summarizer
    
    # Configure from environment variables
    # Map your env vars to external library's expected format
    external_config = {
        'api_key': os.getenv("OPENAI_API_KEY") or os.getenv("EXTERNAL_SUMMARIZER_API_KEY"),
        'model': os.getenv("SUMMARIZER_MODEL", "gpt-4"),
        'temperature': float(os.getenv("SUMMARIZER_TEMPERATURE", "0.7")),
        'max_tokens': int(os.getenv("SUMMARIZER_MAX_TOKENS", "2000"))
    }
    
    # Initialize external summarizer with config
    external_summarizer = Summarizer(**external_config)
    EXTERNAL_AVAILABLE = True
    
except ImportError:
    EXTERNAL_AVAILABLE = False
    external_summarizer = None
    print("⚠ External summarizer not available")

class SummarizeService:
    def __init__(self, use_external: Optional[bool] = None):
        if use_external is None:
            use_external = os.getenv("USE_EXTERNAL_SUMMARIZER", "true").lower() == "true"
        self.use_external = use_external and EXTERNAL_AVAILABLE
    
    def generate_summary_from_text(self, transcript_text: str) -> Dict:
        if self.use_external and external_summarizer:
            return self._generate_with_external(transcript_text)
        else:
            return self._generate_placeholder(transcript_text)
    
    def _generate_with_external(self, transcript_text: str) -> Dict:
        try:
            # Call external summarizer
            result = external_summarizer.summarize(transcript_text)
            
            # Adapt to our format
            return {
                'summary_text': result.get('summary', ''),
                'svg_content': result.get('svg', self._generate_svg_from_summary(result.get('summary', ''))),
                'related_tickers': result.get('tickers', self._extract_tickers(transcript_text))
            }
        except Exception as e:
            print(f"⚠ External summarizer error: {e}, using placeholder")
            return self._generate_placeholder(transcript_text)
```

## Summary: Which Approach to Choose?

| Approach | Best For | Complexity | Recommendation |
|----------|----------|------------|----------------|
| **Option 1: Merge .env** | Most cases | ⭐ Simple | ⭐⭐⭐⭐⭐ **Use this** |
| **Option 2: Programmatic** | Libraries with config API | ⭐⭐ Medium | ⭐⭐⭐⭐ Good alternative |
| **Option 3: Multiple .env** | Special cases only | ⭐⭐⭐ Complex | ⭐⭐ Avoid if possible |
| **Option 4: Prefixes** | Many dependencies | ⭐⭐ Medium | ⭐⭐⭐ Good for organization |
| **Option 5: Config File** | Complex configs | ⭐⭐⭐ Complex | ⭐⭐ Overkill usually |

### Final Recommendation

**Use Option 1 (Merge Environment Variables)** for 95% of cases because:
1. It's the simplest and most maintainable
2. It follows standard Python project practices
3. It works seamlessly with all deployment environments
4. It's easy for other developers to understand
5. It requires minimal code changes

**Only use other options if:**
- The external library **requires** programmatic configuration (Option 2)
- You have **many** external dependencies and need organization (Option 4)
- You have **very complex** nested configurations (Option 5)

## Notes

- **Maintain Interface**: Keep the same input/output format so existing code doesn't break
- **Graceful Degradation**: Always fallback to placeholder if external fails
- **Version Control**: Pin dependencies to avoid breaking changes
- **Documentation**: Update README with new dependency and configuration options
- **Environment Variables**: Merge external repo's required env vars into your `.env` file (recommended)
- **Configuration Priority**: Your `.env` should take precedence over external defaults
- **Security**: Never commit `.env` files - use `.env.example` for documentation

