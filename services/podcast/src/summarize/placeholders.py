"""
Placeholder Generation

Generates placeholder content when external summarization is not available.
"""

import random
from typing import Dict, List

# Placeholder ticker symbols
PLACEHOLDER_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM",
    "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC", "PYPL",
    "NFLX", "ADBE", "CRM", "INTC", "CMCSA", "PEP", "COST", "TMO", "AVGO"
]


def extract_placeholder_tickers() -> List[str]:
    """
    Generate placeholder tickers (random selection).
    
    Returns:
        List of ticker symbols
    """
    num_tickers = random.randint(3, 7)
    return random.sample(PLACEHOLDER_TICKERS, min(num_tickers, len(PLACEHOLDER_TICKERS)))


def generate_placeholder_summary(transcript_length: int) -> str:
    """
    Generate placeholder summary text.
    
    Args:
        transcript_length: Length of transcript (for context)
        
    Returns:
        Placeholder summary markdown text
    """
    # Placeholder summary templates
    templates = [
        """# Podcast Episode Summary

This is a placeholder summary of the podcast episode. The actual summary generation will be implemented in a future update.

## Key Points
- Discussion of market trends and analysis
- Insights into current economic conditions
- Analysis of various investment opportunities

## Main Topics
The episode covers several important topics related to finance and investment strategies.

*Note: This is a placeholder summary. Actual AI-generated summary coming soon.*""",
        
        """# Episode Summary

## Overview
This placeholder summary provides a brief overview of the podcast episode content.

## Highlights
- Market analysis and trends
- Investment strategies discussion
- Economic outlook and predictions

*Placeholder content - real summary generation pending.*""",
        
        """# Summary

This is a placeholder summary for the podcast episode. The transcript contains approximately {length} characters of content.

## Content Summary
The episode discusses various topics including market analysis, investment strategies, and economic trends.

*This is placeholder content. Actual summary will be generated using AI in future updates.*"""
    ]
    
    # Select a random template and format if needed
    template = random.choice(templates)
    if '{length}' in template:
        template = template.format(length=transcript_length)
    
    return template


def generate_placeholder_svg() -> str:
    """
    Generate placeholder SVG content.
    
    Returns:
        SVG XML string
    """
    # Generate random data for the chart
    num_points = random.randint(5, 10)
    points = []
    for i in range(num_points):
        x = 50 + (i * 80)
        y = 200 - random.randint(20, 150)
        points.append(f"{x},{y}")
    
    points_str = " ".join(points)
    
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="300" viewBox="0 0 800 300">
  <rect width="800" height="300" fill="#f5f5f5" stroke="#ddd" stroke-width="2"/>
  <text x="400" y="30" text-anchor="middle" font-family="Arial" font-size="20" font-weight="bold" fill="#333">
    Podcast Episode Visualization
  </text>
  <text x="400" y="50" text-anchor="middle" font-family="Arial" font-size="12" fill="#666">
    (Placeholder Chart)
  </text>
  
  <!-- Chart area -->
  <g transform="translate(50, 70)">
    <!-- Grid lines -->
    <line x1="0" y1="0" x2="0" y2="180" stroke="#ccc" stroke-width="1"/>
    <line x1="0" y1="180" x2="700" y2="180" stroke="#ccc" stroke-width="1"/>
    
    <!-- Data line -->
    <polyline points="{points_str}" fill="none" stroke="#4a90e2" stroke-width="3"/>
    
    <!-- Data points -->
    {_generate_svg_points(points)}
    
    <!-- Y-axis label -->
    <text x="-20" y="90" text-anchor="middle" font-family="Arial" font-size="10" fill="#666" transform="rotate(-90 -20 90)">
      Value
    </text>
    
    <!-- X-axis label -->
    <text x="350" y="210" text-anchor="middle" font-family="Arial" font-size="10" fill="#666">
      Time
    </text>
  </g>
  
  <!-- Legend -->
  <g transform="translate(50, 270)">
    <rect width="15" height="15" fill="#4a90e2"/>
    <text x="25" y="12" font-family="Arial" font-size="12" fill="#333">Episode Data</text>
  </g>
</svg>"""
    
    return svg


def _generate_svg_points(points: List[str]) -> str:
    """
    Generate SVG circle elements for data points.
    
    Args:
        points: List of "x,y" point strings
        
    Returns:
        SVG string with circle elements
    """
    circles = []
    for point in points:
        x, y = map(int, point.split(','))
        circles.append(f'    <circle cx="{x}" cy="{y}" r="5" fill="#4a90e2" stroke="#fff" stroke-width="2"/>')
    
    return "\n".join(circles)


def generate_placeholder_result(transcript_text: str) -> Dict:
    """
    Generate placeholder summary, SVG, and tickers (fallback method).
    
    Args:
        transcript_text: Transcript text content (string)
        
    Returns:
        Dictionary with placeholder content
    """
    transcript_length = len(transcript_text)
    
    # Generate placeholder summary
    summary_text = generate_placeholder_summary(transcript_length)
    
    # Generate placeholder SVG
    svg_content = generate_placeholder_svg()
    
    # Generate placeholder tickers
    related_tickers = extract_placeholder_tickers()
    
    return {
        'summary_text': summary_text,
        'svg_content': svg_content,
        'related_tickers': related_tickers
    }
