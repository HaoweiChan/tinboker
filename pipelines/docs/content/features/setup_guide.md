# Setup Guide: Podcast Analysis Agents

This guide explains how to set up and configure the Podcast Analysis Agents system.

## Prerequisites

- Python 3.10 or higher
- pip package manager

## Installation

1. Clone the repository and navigate to the project directory:

```bash
cd Graph-Builder-Agent
```

2. Install the package in development mode:

```bash
pip install -e ".[dev]"
```

## API Keys Configuration

The system requires API keys for the following services:

### 1. OpenAI API (Required for LLM features)

**Purpose**: Powers the Extractor, Researcher, and Writer agents for event extraction, research synthesis, and report generation.

**How to get**:
1. Sign up at [OpenAI Platform](https://platform.openai.com/)
2. Navigate to API Keys section
3. Create a new secret key

**Configuration**:
```bash
export OPENAI_API_KEY="sk-your-openai-api-key-here"
```

**Supported Models**:
- `gpt-5.2` (default, recommended)
- `gpt-4-turbo`
- `gpt-4`
- `gpt-3.5-turbo`

**Cost Considerations**:
- Event extraction: ~2,000-5,000 tokens per transcript
- Research queries: ~500-1,000 tokens per gap
- Report generation: ~2,000-4,000 tokens per report

### 2. Anthropic API (Optional alternative LLM)

**Purpose**: Alternative LLM provider, especially good for the Writer agent.

**How to get**:
1. Sign up at [Anthropic Console](https://console.anthropic.com/)
2. Navigate to API Keys
3. Create a new key

**Configuration**:
```bash
export ANTHROPIC_API_KEY="sk-ant-your-anthropic-api-key-here"
```

**Supported Models**:
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`

### 3. Tavily API (Required for Research features)

**Purpose**: Powers the Researcher agent for web searches to fill information gaps with external sources.

**How to get**:
1. Sign up at [Tavily](https://tavily.com/)
2. Navigate to your dashboard
3. Copy your API key

**Configuration**:
```bash
export TAVILY_API_KEY="tvly-your-tavily-api-key-here"
```

**Features**:
- Optimized for LLM agent use
- Returns structured search results
- Includes source credibility signals

**Free Tier**: 1,000 searches/month

## Environment Configuration

### Option 1: Export in Terminal

```bash
export OPENAI_API_KEY="sk-..."
export TAVILY_API_KEY="tvly-..."
# Optional
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Option 2: Create .env File

Create a `.env` file in the project root:

```env
# Required
OPENAI_API_KEY=sk-your-openai-api-key
TAVILY_API_KEY=tvly-your-tavily-api-key

# Optional
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key
LOG_LEVEL=INFO
```

Then load it before running:

```bash
source .env  # or use python-dotenv
```

### Option 3: Configuration File

Edit `configs/default.yaml` to change default models and settings:

```yaml
llm:
  default_provider: openai
  extractor_model: gpt-5.2
  researcher_model: gpt-5.2
  writer_model: gpt-5.2
  temperatures:
    extractor: 0.1
    researcher: 0.0
    writer: 0.4

search:
  default_engine: tavily
  timeout_seconds: 30
```

## Running Without API Keys

The system can run in **limited mode** without API keys:

### Preprocessor Only (No API keys needed)

```bash
python scripts/run_pipeline.py preprocess input.txt
```

This will:
- Add line numbers to transcript
- Detect language
- Identify speakers (if format supports it)
- Mark segment boundaries

### Validation Only (No API keys needed)

```bash
python scripts/run_pipeline.py validate input.txt
```

## Feature Availability by API Key

| Feature | No Keys | OpenAI Only | Tavily Only | Both |
|---------|---------|-------------|-------------|------|
| Preprocessing | ✅ | ✅ | ✅ | ✅ |
| Event Extraction | ❌ | ✅ | ❌ | ✅ |
| Gap Research | ❌ | ❌ | ⚠️ Limited | ✅ |
| Report Generation | ⚠️ Basic | ✅ | ⚠️ Basic | ✅ |

## Verifying Setup

Run this command to verify your setup:

```bash
python -c "
import os
print('OpenAI API Key:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')
print('Tavily API Key:', 'SET' if os.getenv('TAVILY_API_KEY') else 'NOT SET')
print('Anthropic API Key:', 'SET' if os.getenv('ANTHROPIC_API_KEY') else 'NOT SET')
"
```

## Quick Start

Once API keys are configured:

```bash
# Run full pipeline on a transcript
python scripts/run_pipeline.py run "data/transcripts/CNBC's Fast Money/0001_Can Oracle Get Shares Back in Rally Mode, and a Trade School on the Netflix_Warner Brothers Deal 12_5_25.txt" -o outputs/report.md

# View the generated report
cat outputs/report.md
```

## Troubleshooting

### "OpenAI API key not provided"

Make sure the environment variable is set:
```bash
echo $OPENAI_API_KEY
```

### "Tavily API key not provided"

The Researcher agent requires Tavily for web searches:
```bash
export TAVILY_API_KEY="tvly-..."
```

### Rate Limits

If you hit rate limits:
1. Wait and retry
2. Use a lower-tier model (e.g., `gpt-3.5-turbo`)
3. Reduce `max_searches_per_event` in config

### Connection Errors

Check your internet connection and firewall settings. The system needs access to:
- `api.openai.com`
- `api.anthropic.com`
- `api.tavily.com`

