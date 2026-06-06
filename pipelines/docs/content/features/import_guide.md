# Import Guide: Using Podcast Analysis Agents as a Library

This guide explains how to import and use the Podcast Analysis Agents project as a Python library in your own projects.

## Table of Contents

- [Installation](#installation)
- [Updating the Package](#updating-the-package)
- [Basic Import Patterns](#basic-import-patterns)
- [Using the Orchestrator](#using-the-orchestrator)
- [Using Individual Agents](#using-individual-agents)
- [Working with Models](#working-with-models)
- [Using Services](#using-services)
- [Configuration](#configuration)
- [Complete Examples](#complete-examples)

## Installation

### Option 1: Install from Local Directory

If you have the project locally:

```bash
cd /path/to/Content-Builder
pip install -e ".[dev]"
```

### Option 2: Install from Git Repository

```bash
pip install git+https://github.com/Graphfolio/Content-Builder.git
```

### Option 3: Add to Your Project's Dependencies

In your `pyproject.toml` or `requirements.txt`:

```toml
# pyproject.toml
[project]
dependencies = [
    "podcast-analysis-agents @ git+https://github.com/Graphfolio/Content-Builder.git",
]
```

## Updating the Package

When the project receives updates (new commits, bug fixes, features), you need to update your installation. The method depends on how you installed it.

### Scenario 1: Editable Install (Development Mode)

If you installed with `pip install -e .` (editable/development mode):

**Good news**: Updates are **automatic**! Since the package points directly to the source code, any changes you pull from the repository are immediately available.

```bash
# Navigate to the project directory
cd /path/to/Content-Builder

# Pull latest changes
git pull origin main

# That's it! The changes are already available
# No need to reinstall
```

**Note**: If new dependencies were added, you may need to:
```bash
pip install -e ".[dev]"  # Reinstall to get new dependencies
```

### Scenario 2: Git Repository Install

If you installed from a git repository:

```bash
# Option A: Update to latest from main/master branch
pip install --upgrade --force-reinstall git+https://github.com/Graphfolio/Content-Builder.git

# Option B: Update to a specific branch
pip install --upgrade --force-reinstall git+https://github.com/Graphfolio/Content-Builder.git@develop

# Option C: Update to a specific commit/tag
pip install --upgrade --force-reinstall git+https://github.com/Graphfolio/Content-Builder.git@v0.2.0
```

### Scenario 3: Local Directory (Non-Editable)

If you installed from a local directory without `-e` flag:

```bash
# Navigate to the project directory
cd /path/to/Content-Builder

# Pull latest changes
git pull origin main

# Reinstall the package
pip install --upgrade --force-reinstall .
```

### Scenario 4: Installed as Dependency in Another Project

If you added it to your project's `pyproject.toml` or `requirements.txt`:

**Option A: Update to latest**
```bash
# In your project directory
pip install --upgrade "podcast-analysis-agents @ git+https://github.com/Graphfolio/Content-Builder.git"
```

**Option B: Pin to specific version/tag**
```toml
# pyproject.toml
[project]
dependencies = [
    "podcast-analysis-agents @ git+https://github.com/your-org/Content-Builder.git@v0.2.0",
]
```

Then update:
```bash
pip install --upgrade -e .
```

### Scenario 5: PyPI Package (Future)

If the package is published to PyPI:

```bash
# Update to latest version
pip install --upgrade podcast-analysis-agents

# Update to specific version
pip install --upgrade podcast-analysis-agents==0.2.0
```

### Verifying the Update

After updating, verify you have the latest version:

```python
# Check installed version
import src
print(src.__version__)  # Should show the updated version

# Or check via pip
pip show podcast-analysis-agents
```

### Troubleshooting Updates

**Issue**: Changes not appearing after update

**Solution**: 
```bash
# Clear Python cache
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# Reinstall
pip install --upgrade --force-reinstall -e .
```

**Issue**: Import errors after update

**Solution**: Check if new dependencies were added:
```bash
# Reinstall with all dependencies
pip install -e ".[dev]"
```

**Issue**: Version conflicts

**Solution**: Use a virtual environment:
```bash
# Create fresh virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Best Practices for Updates

1. **Use Editable Installs for Development**: If you're actively developing or frequently pulling updates, use `pip install -e .` for automatic updates.

2. **Pin Versions in Production**: For production deployments, pin to specific commits or tags:
   ```toml
   dependencies = [
       "podcast-analysis-agents @ git+https://github.com/your-org/Content-Builder.git@abc123def",
   ]
   ```

3. **Test After Updates**: Always test your code after updating to ensure compatibility:
   ```bash
   pytest  # Run your tests
   ```

4. **Check Changelog**: Review release notes or commit messages to understand what changed.

5. **Use Virtual Environments**: Isolate updates to avoid conflicts with other projects.

## Basic Import Patterns

The package is organized into several main modules:

```python
# Simple API (recommended for quick usage)
from content_builder.api import analyze_transcript

# Core orchestrator (recommended for advanced use cases)
from content_builder.agents.orchestrator import Orchestrator

# Individual agents
from content_builder.agents.preprocessor import Preprocessor
from content_builder.agents.extractor import ExtractorAgent
from content_builder.agents.writer import WriterAgent

# Models (data structures)
from content_builder.models.event import Event, EventList, Evidence
from content_builder.models.transcript import PreprocessedTranscript, PreprocessorOutput
from content_builder.models.output import MarkdownReport

# Services (LLM and search clients)
from content_builder.services.llm import OpenAIClient, BaseLLMClient
from content_builder.services.search import TavilyClient, BaseSearchClient

# Configuration
from content_builder.utils.config import Config, load_config

# Utilities
from content_builder.utils.transcript import add_line_numbers, detect_speakers
```

## Simple API (Quick Start)

For the simplest use case - just pass a transcript string and get a markdown report back:

```python
from content_builder.api import analyze_transcript

# Simple usage
transcript = "Speaker 1: Hello world. Speaker 2: Hi there..."

report = analyze_transcript(
    transcript=transcript,
    source="My Podcast",
    episode_title="Episode 1"
)

print(report)  # Markdown string
```

**Key Features:**
- ✅ Pure function: input string → output string
- ✅ No file I/O: no intermediate files saved
- ✅ Simple interface: just pass transcript and optional metadata
- ✅ Uses environment variables for API keys by default
- ✅ Can override API keys via parameters

**With explicit API keys:**
```python
report = analyze_transcript(
    transcript=transcript,
    source="My Podcast",
    episode_title="Episode 1",
    openai_api_key="sk-your-key",
    tavily_api_key="tvly-your-key"
)
```

**With custom config:**
```python
from pathlib import Path

report = analyze_transcript(
    transcript=transcript,
    source="My Podcast",
    config_path=Path("configs/custom.yaml")
)
```

## Using the Orchestrator

The `Orchestrator` provides more control and is recommended for advanced use cases. It coordinates all agents in the pipeline.

### Basic Usage

```python
import asyncio
from content_builder.agents.orchestrator import Orchestrator
from content_builder.services.llm import OpenAIClient
from content_builder.services.search import TavilyClient
from content_builder.utils.config import load_config

# Load configuration
config = load_config()

# Initialize clients
llm_client = OpenAIClient(api_key="sk-your-key-here")
search_client = TavilyClient(api_key="tvly-your-key-here")

# Create orchestrator
orchestrator = Orchestrator(
    config=config,
    llm_client=llm_client,
    search_client=search_client,
)

# Run the full pipeline
async def process_transcript():
    with open("transcript.txt", "r") as f:
        raw_transcript = f.read()
    
    report = await orchestrator.run(
        raw_transcript=raw_transcript,
        source="CNBC Fast Money",
        episode_title="Market Analysis Episode 1",
        filename="transcript.txt",
    )
    
    # Save the report
    report.to_file("output/report.md")
    
    # Access report metadata
    print(f"Word count: {report.writer_meta.word_count}")
    print(f"Events covered: {report.writer_meta.events_covered}")
    print(f"Citations: {report.writer_meta.citations_count}")

# Run async function
asyncio.run(process_transcript())
```

### Synchronous Wrapper

For convenience, the orchestrator also provides a synchronous method:

```python
from content_builder.agents.orchestrator import Orchestrator

orchestrator = Orchestrator(
    config=load_config(),
    llm_client=OpenAIClient(api_key="sk-..."),
    search_client=TavilyClient(api_key="tvly-..."),
)

# Synchronous call (handles async internally)
report = orchestrator.run_sync(
    raw_transcript=raw_transcript,
    source="CNBC Fast Money",
    episode_title="Episode 1",
    filename="transcript.txt",
    output_dir="outputs/episode_1",
    save_intermediate=True,  # Save all stage outputs as JSON
)

report.to_file("outputs/report.md")
```

### Running Individual Stages

You can also run individual pipeline stages:

```python
from content_builder.agents.preprocessor.preprocessor import PreprocessorInput

# Run preprocessing stage
preprocessor_input = PreprocessorInput(
    raw_transcript=raw_transcript,
    source="CNBC Fast Money",
    filename="transcript.txt",
)

preprocessed = await orchestrator.run_stage("preprocess", preprocessor_input)

# Run extraction stage (requires preprocessed output)
events = await orchestrator.run_stage("extract", preprocessed)

# Run writing stage (requires extracted events)
report = await orchestrator.run_stage("write", events)
```

## Using Individual Agents

You can use agents independently for more fine-grained control.

### Preprocessor

```python
from content_builder.agents.preprocessor import Preprocessor
from content_builder.agents.preprocessor.preprocessor import PreprocessorInput

preprocessor = Preprocessor(
    config=config.preprocessor,
    llm_client=llm_client,
)

input_data = PreprocessorInput(
    raw_transcript="Your transcript text here...",
    source="Podcast Name",
    filename="transcript.txt",
)

result = await preprocessor.process(input_data)

# Access preprocessed data
print(f"Total lines: {result.prepared_transcript.total_lines}")
print(f"Speakers: {result.prepared_transcript.speakers}")
print(f"Language: {result.prepared_transcript.language}")
print(f"Numbered text:\n{result.prepared_transcript.numbered_text}")
```

### Extractor Agent

```python
from content_builder.agents.extractor import ExtractorAgent
from content_builder.models.transcript import PreprocessorOutput

extractor = ExtractorAgent(
    config=config.extractor,
    llm_client=llm_client,
)

# Requires preprocessed transcript
extractor_input = PreprocessorOutput(
    prepared_transcript=preprocessed_result.prepared_transcript,
    validation=preprocessed_result.validation,
)

events = await extractor.process(extractor_input)

# Access extracted events
for event in events.events:
    print(f"Event: {event.what}")
    print(f"Confidence: {event.confidence}")
    print(f"Evidence lines: {event.evidence[0].line_start}-{event.evidence[0].line_end}")
```

### Writer Agent

```python
from content_builder.agents.writer import WriterAgent
from content_builder.models.event import EventList

writer = WriterAgent(
    config=config.writer,
    llm_client=llm_client,
)

# Requires extracted events
writer_input = EventList(events=extracted_events.events)

report = await writer.process(writer_input)

# Access the markdown report
print(report.report.markdown)
report.report.to_file("output/report.md")
```

## Working with Models

The package uses Pydantic models for type safety and validation.

### Event Models

```python
from content_builder.models.event import Event, Evidence, EventList

# Create an event manually
event = Event(
    what="Company announces new product",
    why="To capture market share",
    what_changed="Product launch scheduled for Q2",
    who_affected=["COMPANY", "COMPETITOR"],
    evidence=[
        Evidence(
            quote="We're launching our new product in Q2",
            line_start=42,
            line_end=45,
            confidence=0.95,
        )
    ],
    confidence=0.9,
    tickers=["COMPANY"],
)

# Create event list
event_list = EventList(events=[event])
```

### Transcript Models

```python
from content_builder.models.transcript import (
    PreprocessedTranscript,
    Speaker,
    SegmentHint,
    EventBlock,
)

# Create preprocessed transcript
transcript = PreprocessedTranscript(
    numbered_text="1: Speaker 1: Hello\n2: Speaker 2: Hi there",
    total_lines=2,
    language="en",
    speakers=[
        Speaker(name="Speaker 1", role="host", line_start=1, line_end=1),
        Speaker(name="Speaker 2", role="guest", line_start=2, line_end=2),
    ],
    segment_hints=[
        SegmentHint(
            type="topic_change",
            line_start=10,
            line_end=15,
            description="Discussion shifts to earnings",
        )
    ],
)
```

### Report Models

```python
from content_builder.models.output import MarkdownReport, WriterMeta

report = MarkdownReport(
    markdown="# Report Title\n\nContent here...",
    writer_meta=WriterMeta(
        word_count=1500,
        events_covered=5,
        citations_count=12,
        tickers_mentioned=["AAPL", "MSFT"],
    ),
)

# Save to file
report.to_file("output/report.md")

# Access properties
print(report.markdown)
print(report.writer_meta.word_count)
```

## Using Services

### LLM Clients

```python
from content_builder.services.llm import OpenAIClient, BaseLLMClient

# Initialize OpenAI client
llm_client = OpenAIClient(api_key="sk-your-key")

# Make a completion request
response = await llm_client.complete(
    prompt="Extract key events from this transcript...",
    model="gpt-5.2",
    temperature=0.1,
    max_tokens=2000,
)

print(response.content)
print(response.model)
print(response.usage)
```

### Search Clients

```python
from content_builder.services.search import TavilyClient
from datetime import date

search_client = TavilyClient(api_key="tvly-your-key")

# Perform a search
results = await search_client.search(
    query="Apple earnings Q4 2024",
    max_results=5,
    recency_days=30,
)

for result in results.results:
    print(f"Title: {result.title}")
    print(f"URL: {result.url}")
    print(f"Content: {result.content[:200]}...")
    print(f"Score: {result.score}")
```

### Custom Service Implementations

You can implement custom clients by extending the base classes:

```python
from content_builder.services.llm.base import BaseLLMClient, LLMResponse

class CustomLLMClient(BaseLLMClient):
    async def complete(
        self,
        prompt: str,
        model: str = "custom-model",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> LLMResponse:
        # Your custom implementation
        response_text = await your_custom_api_call(prompt, model)
        
        return LLMResponse(
            content=response_text,
            model=model,
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
```

## Configuration

### Loading Configuration

```python
from content_builder.utils.config import Config, load_config

# Load default configuration
config = load_config()

# Load from custom path
config = load_config("configs/custom.yaml")

# Access configuration sections
print(config.preprocessor.max_line_length)
print(config.extractor.max_events)
print(config.writer.max_sections)
```

### Customizing Configuration

```python
from content_builder.utils.config import Config, load_config, merge_configs

# Load base config
base_config = load_config()

# Create override
override = {
    "extractor": {
        "max_events": 30,  # Increase max events
        "min_event_confidence": 0.6,  # Lower confidence threshold
    },
    "llm": {
        "extractor_model": "gpt-4-turbo",  # Use different model
    },
}

# Merge configurations
custom_config = merge_configs(base_config, override)

# Use custom config
orchestrator = Orchestrator(
    config=custom_config,
    llm_client=llm_client,
)
```

## Complete Examples

### Example 1: Using Simple API (Recommended for Quick Start)

```python
"""Simplest example: Use the analyze_transcript function."""

from content_builder.api import analyze_transcript

# Read transcript (or get it from anywhere)
transcript = """
Speaker 1: Welcome to today's show. We're discussing the latest market trends.
Speaker 2: Yes, and we've seen significant movement in tech stocks this week.
Speaker 1: Let's dive into Apple's earnings announcement.
Speaker 2: Apple reported strong iPhone sales, beating expectations.
"""

# Analyze and get report (no file I/O, pure function)
report = analyze_transcript(
    transcript=transcript,
    source="Market Talk Podcast",
    episode_title="Weekly Market Review"
)

# Use the report
print(report)  # Markdown string

# Or save it if needed
with open("report.md", "w") as f:
    f.write(report)
```

### Example 2: Simple Pipeline with Orchestrator

```python
"""Simple example: Process a transcript and generate a report."""

import asyncio
import os
from pathlib import Path

from content_builder.agents.orchestrator import Orchestrator
from content_builder.services.llm import OpenAIClient
from content_builder.services.search import TavilyClient
from content_builder.utils.config import load_config


async def main():
    # Setup
    config = load_config()
    llm_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    search_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    
    orchestrator = Orchestrator(
        config=config,
        llm_client=llm_client,
        search_client=search_client,
    )
    
    # Read transcript
    transcript_path = Path("data/transcript.txt")
    raw_transcript = transcript_path.read_text()
    
    # Process
    report = await orchestrator.run(
        raw_transcript=raw_transcript,
        source="My Podcast",
        episode_title="Episode 1",
        filename=transcript_path.name,
    )
    
    # Save output
    output_path = Path("outputs/report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_file(str(output_path))
    
    print(f"Report saved to {output_path}")
    print(f"Events: {report.writer_meta.events_covered}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Example 3: Batch Processing

```python
"""Process multiple transcripts in batch."""

import asyncio
from pathlib import Path

from content_builder.agents.orchestrator import Orchestrator
from content_builder.services.llm import OpenAIClient
from content_builder.services.search import TavilyClient
from content_builder.utils.config import load_config


async def process_file(orchestrator, file_path, output_dir):
    """Process a single transcript file."""
    raw_transcript = file_path.read_text()
    
    report = await orchestrator.run(
        raw_transcript=raw_transcript,
        source="Batch Podcast",
        episode_title=file_path.stem,
        filename=file_path.name,
    )
    
    output_path = output_dir / f"{file_path.stem}_report.md"
    report.to_file(str(output_path))
    return output_path


async def main():
    # Setup
    config = load_config()
    llm_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    search_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    
    orchestrator = Orchestrator(
        config=config,
        llm_client=llm_client,
        search_client=search_client,
    )
    
    # Find all transcripts
    input_dir = Path("data/transcripts")
    output_dir = Path("outputs/batch")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    transcript_files = list(input_dir.glob("*.txt"))
    
    # Process all files
    tasks = [
        process_file(orchestrator, file_path, output_dir)
        for file_path in transcript_files
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Report results
    successful = sum(1 for r in results if not isinstance(r, Exception))
    failed = len(results) - successful
    
    print(f"Processed {successful} files successfully")
    if failed > 0:
        print(f"{failed} files failed")


if __name__ == "__main__":
    asyncio.run(main())
```

### Example 4: Custom Pipeline with Individual Agents

```python
"""Custom pipeline with fine-grained control over each stage."""

import asyncio
from pathlib import Path

from content_builder.agents.preprocessor import Preprocessor
from content_builder.agents.preprocessor.preprocessor import PreprocessorInput
from content_builder.agents.extractor import ExtractorAgent
from content_builder.agents.writer import WriterAgent
from content_builder.services.llm import OpenAIClient
from content_builder.utils.config import load_config


async def main():
    config = load_config()
    llm_client = OpenAIClient(api_key=os.getenv("OPENAI_API_KEY"))
    
    # Initialize agents
    preprocessor = Preprocessor(
        config=config.preprocessor,
        llm_client=llm_client,
    )
    
    extractor = ExtractorAgent(
        config=config.extractor,
        llm_client=llm_client,
    )
    
    writer = WriterAgent(
        config=config.writer,
        llm_client=llm_client,
    )
    
    # Read transcript
    raw_transcript = Path("data/transcript.txt").read_text()
    
    # Stage 1: Preprocess
    print("Preprocessing...")
    preprocessor_input = PreprocessorInput(
        raw_transcript=raw_transcript,
        source="Custom Pipeline",
        filename="transcript.txt",
    )
    preprocessed = await preprocessor.process(preprocessor_input)
    print(f"Preprocessed: {preprocessed.prepared_transcript.total_lines} lines")
    
    # Stage 2: Extract events
    print("Extracting events...")
    events = await extractor.process(preprocessed)
    print(f"Extracted {len(events.events)} events")
    
    # Stage 3: Generate report
    print("Writing report...")
    report = await writer.process(events)
    print(f"Report generated: {report.report.writer_meta.word_count} words")
    
    # Save output
    report.report.to_file("outputs/custom_report.md")
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Example 5: Using Models Directly

```python
"""Work with models directly without running the pipeline."""

from content_builder.models.event import Event, Evidence, EventList
from content_builder.models.output import MarkdownReport, WriterMeta


# Create events manually
events = EventList(events=[
    Event(
        what="Company announces earnings beat",
        why="Strong revenue growth in cloud division",
        what_changed="Stock price up 5% in after-hours trading",
        who_affected=["COMPANY", "COMPETITOR"],
        evidence=[
            Evidence(
                quote="We're pleased to report earnings of $2.50 per share",
                line_start=100,
                line_end=105,
                confidence=0.95,
            )
        ],
        confidence=0.9,
        tickers=["COMPANY"],
    ),
])

# Create a report manually
report = MarkdownReport(
    markdown="# Market Analysis\n\n## Key Events\n\n...",
    writer_meta=WriterMeta(
        word_count=1500,
        events_covered=1,
        citations_count=3,
        tickers_mentioned=["COMPANY"],
    ),
)

# Save report
report.to_file("outputs/manual_report.md")
```

## Error Handling

```python
from content_builder.agents.orchestrator import Orchestrator
from content_builder.models.pipeline import PipelineError

try:
    report = await orchestrator.run(
        raw_transcript=transcript,
        source="Podcast",
    )
except Exception as e:
    print(f"Pipeline failed: {e}")
    # Access state manager for error details
    if orchestrator.state_manager.current_state:
        errors = orchestrator.state_manager.current_state.errors
        for error in errors:
            print(f"Error at stage {error.stage}: {error.message}")
```

## Best Practices

1. **Use the Orchestrator**: For most use cases, use `Orchestrator` rather than individual agents. It handles state management and error recovery.

2. **Reuse Clients**: Initialize LLM and search clients once and reuse them across multiple runs to avoid re-authentication overhead.

3. **Handle Async Properly**: All agent methods are async. Use `asyncio.run()` or `await` appropriately.

4. **Save Intermediate Outputs**: Use `save_intermediate=True` when debugging to inspect stage outputs.

5. **Customize Configuration**: Adjust configuration based on your use case (model selection, temperature, max events, etc.).

6. **Type Hints**: The package uses Pydantic models with full type hints. Use them for better IDE support and type checking.

## Troubleshooting

### Import Errors

If you get import errors, make sure the package is installed:

```bash
pip install -e ".[dev]"
```

### Module Not Found

If `src` module is not found, ensure you're importing from the installed package, not the local directory. The package should be installed with `pip install -e .`.

### API Key Errors

Make sure API keys are set in environment variables:

```python
import os
os.environ["OPENAI_API_KEY"] = "sk-..."
os.environ["TAVILY_API_KEY"] = "tvly-..."
```

## Additional Resources

- [Setup Guide](setup_guide.md) - API key configuration and setup
- [README](../README.md) - Project overview and CLI usage
- Source code in `src/` - Full API documentation in docstrings

