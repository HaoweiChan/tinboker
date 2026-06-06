#!/usr/bin/env python3
"""
Analyze word gaps in transcript to identify patterns for sentence segmentation.

This script:
1. Loads transcript JSON with word-level timestamps
2. Calculates gaps between consecutive words
3. Draws histograms to visualize gap distributions
4. Calculates statistics to help identify sentence boundaries
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np


def load_transcript(transcript_path: Path) -> Dict:
    """Load transcript JSON file."""
    with open(transcript_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def calculate_word_gaps(words: List[Dict]) -> List[float]:
    """
    Calculate gaps between consecutive words.
    
    Gap = next_word.start - current_word.end
    
    Args:
        words: List of word dictionaries with 'start' and 'end' keys
        
    Returns:
        List of gap durations in milliseconds
    """
    gaps = []
    
    for i in range(len(words) - 1):
        current_word = words[i]
        next_word = words[i + 1]
        
        # Calculate gap: time between end of current word and start of next word
        gap = next_word['start'] - current_word['end']
        gaps.append(gap)
    
    return gaps


def calculate_word_durations(words: List[Dict]) -> List[float]:
    """Calculate duration of each word."""
    durations = []
    for word in words:
        duration = word['end'] - word['start']
        durations.append(duration)
    return durations


def calculate_moving_stats(words: List[Dict], window_size: int = 8) -> List[Dict]:
    """
    Calculate moving average and standard deviation for each word position.
    
    For each word i, calculates stats from words [i-window_size : i-1].
    
    Args:
        words: List of word dictionaries with 'start' and 'end' keys
        window_size: Number of previous words to include in moving window
        
    Returns:
        List of dictionaries, each containing:
        - 'word_idx': Index of the word
        - 'duration': Word duration in ms
        - 'moving_avg': Moving average of previous window_size words
        - 'moving_std': Moving standard deviation of previous window_size words
        - 'z_score': Z-score of current word duration
        - 'window_durations': List of durations in the window (for reference)
    """
    durations = calculate_word_durations(words)
    moving_stats = []
    
    for i in range(len(words)):
        duration = durations[i]
        
        # Get window of previous words
        window_start = max(0, i - window_size)
        window_end = i
        window_durations = durations[window_start:window_end]
        
        # Calculate moving stats
        if len(window_durations) > 0:
            moving_avg = float(np.mean(window_durations))
            moving_std = float(np.std(window_durations))
            
            # Calculate z-score (handle zero std case)
            if moving_std > 0:
                z_score = (duration - moving_avg) / moving_std
            else:
                z_score = 0.0 if duration == moving_avg else float('inf')
        else:
            # First word(s) - no previous words to compare
            moving_avg = duration
            moving_std = 0.0
            z_score = 0.0
            window_durations = []
        
        moving_stats.append({
            'word_idx': i,
            'duration': duration,
            'moving_avg': moving_avg,
            'moving_std': moving_std,
            'z_score': z_score,
            'window_durations': window_durations
        })
    
    return moving_stats


def detect_duration_anomalies(
    words: List[Dict],
    window_size: int = 8,
    z_threshold: float = 2.0,
    min_words_before: int = 3,
    require_longer_than_neighbors: bool = True,
    neighbor_ratio_threshold: float = 1.5
) -> List[Dict]:
    """
    Detect words with unusually long durations (potential sentence boundaries).
    
    Args:
        words: List of word dictionaries
        window_size: Size of moving window for statistics
        z_threshold: Z-score threshold for detecting anomalies
        min_words_before: Minimum number of words before first boundary
        require_longer_than_neighbors: If True, word must be longer than both previous and next words
        neighbor_ratio_threshold: Ratio threshold for neighbor comparison (default: 1.5x)
        
    Returns:
        List of anomaly dictionaries, each containing:
        - 'word_idx': Index of anomalous word
        - 'word': Word dictionary
        - 'z_score': Z-score value
        - 'duration': Word duration
        - 'moving_avg': Moving average at this position
        - 'prev_duration': Previous word duration
        - 'next_duration': Next word duration
        - 'confidence': Confidence level (based on z-score and neighbor comparison)
    """
    moving_stats = calculate_moving_stats(words, window_size)
    durations = calculate_word_durations(words)
    anomalies = []
    
    for i, stats in enumerate(moving_stats):
        z_score = stats['z_score']
        current_duration = stats['duration']
        
        # Check if this is an anomaly based on z-score
        is_z_anomaly = (z_score >= z_threshold and 
                       i >= min_words_before and
                       not np.isinf(z_score) and
                       not np.isnan(z_score))
        
        if not is_z_anomaly:
            continue
        
        # Additional check: must be longer than both previous and next words
        if require_longer_than_neighbors:
            # Get previous word duration
            prev_duration = durations[i - 1] if i > 0 else None
            # Get next word duration
            next_duration = durations[i + 1] if i < len(words) - 1 else None
            
            # Check if current word is significantly longer than both neighbors
            longer_than_prev = True
            longer_than_next = True
            
            if prev_duration is not None:
                longer_than_prev = current_duration >= prev_duration * neighbor_ratio_threshold
            
            if next_duration is not None:
                longer_than_next = current_duration >= next_duration * neighbor_ratio_threshold
            
            # Must be longer than both neighbors (or at least one if at boundary)
            if not (longer_than_prev and longer_than_next):
                # If we're at the start or end, be more lenient
                if i == 0 and longer_than_next:
                    pass  # OK at start
                elif i == len(words) - 1 and longer_than_prev:
                    pass  # OK at end
                else:
                    continue  # Skip this word - not longer than both neighbors
        else:
            prev_duration = durations[i - 1] if i > 0 else None
            next_duration = durations[i + 1] if i < len(words) - 1 else None
        
        # Calculate confidence based on z-score and neighbor comparison
        if z_score >= 2.5:
            base_confidence = 'high'
        elif z_score >= 2.0:
            base_confidence = 'medium'
        else:
            base_confidence = 'low'
        
        # Boost confidence if significantly longer than both neighbors
        if require_longer_than_neighbors:
            if prev_duration and next_duration:
                ratio_prev = current_duration / prev_duration if prev_duration > 0 else 0
                ratio_next = current_duration / next_duration if next_duration > 0 else 0
                if ratio_prev >= 2.0 and ratio_next >= 2.0:
                    confidence = 'high'
                elif ratio_prev >= 1.5 and ratio_next >= 1.5:
                    confidence = base_confidence if base_confidence != 'low' else 'medium'
                else:
                    confidence = base_confidence
            else:
                confidence = base_confidence
        else:
            confidence = base_confidence
        
        anomalies.append({
            'word_idx': i,
            'word': words[i],
            'z_score': z_score,
            'duration': current_duration,
            'moving_avg': stats['moving_avg'],
            'moving_std': stats['moving_std'],
            'prev_duration': prev_duration,
            'next_duration': next_duration,
            'confidence': confidence
        })
    
    return anomalies


def calculate_statistics(values: List[float], name: str = "values") -> Dict:
    """Calculate statistical measures."""
    if not values:
        return {}
    
    values_array = np.array(values)
    
    stats = {
        'count': len(values),
        'mean': float(np.mean(values_array)),
        'median': float(np.median(values_array)),
        'std': float(np.std(values_array)),
        'min': float(np.min(values_array)),
        'max': float(np.max(values_array)),
        'percentiles': {
            'p25': float(np.percentile(values_array, 25)),
            'p50': float(np.percentile(values_array, 50)),
            'p75': float(np.percentile(values_array, 75)),
            'p90': float(np.percentile(values_array, 90)),
            'p95': float(np.percentile(values_array, 95)),
            'p99': float(np.percentile(values_array, 99)),
        }
    }
    
    return stats


def plot_histogram(
    values: List[float],
    title: str,
    xlabel: str,
    ylabel: str = "Frequency",
    bins: int = 50,
    xlim: Tuple[float, float] = None,
    save_path: Path = None
):
    """Plot histogram of values."""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Filter out negative values (shouldn't happen, but just in case)
    values_clean = [v for v in values if v >= 0]
    
    ax.hist(values_clean, bins=bins, edgecolor='black', alpha=0.7)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.grid(True, alpha=0.3)
    
    if xlim:
        ax.set_xlim(xlim)
    
    # Add statistics as text
    if values_clean:
        stats = calculate_statistics(values_clean)
        stats_text = (
            f"Mean: {stats['mean']:.1f} ms\n"
            f"Median: {stats['median']:.1f} ms\n"
            f"Std: {stats['std']:.1f} ms\n"
            f"P95: {stats['percentiles']['p95']:.1f} ms\n"
            f"P99: {stats['percentiles']['p99']:.1f} ms"
        )
        ax.text(0.98, 0.98, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  Saved histogram to: {save_path}")
    else:
        plt.show()
    
    plt.close()


def plot_log_histogram(
    values: List[float],
    title: str,
    xlabel: str,
    ylabel: str = "Frequency",
    bins: int = 50,
    save_path: Path = None
):
    """Plot histogram with log scale on x-axis."""
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Filter out negative and zero values for log scale
    values_clean = [v for v in values if v > 0]
    
    ax.hist(values_clean, bins=bins, edgecolor='black', alpha=0.7)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_xscale('log')
    ax.grid(True, alpha=0.3, which='both')
    
    # Add statistics as text
    if values_clean:
        stats = calculate_statistics(values_clean)
        stats_text = (
            f"Mean: {stats['mean']:.1f} ms\n"
            f"Median: {stats['median']:.1f} ms\n"
            f"P95: {stats['percentiles']['p95']:.1f} ms\n"
            f"P99: {stats['percentiles']['p99']:.1f} ms"
        )
        ax.text(0.98, 0.98, stats_text, transform=ax.transAxes,
                fontsize=10, verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  Saved log histogram to: {save_path}")
    else:
        plt.show()
    
    plt.close()


def plot_word_sequence(
    words: List[Dict],
    sentences: List[Dict] = None,
    gaps: List[float] = None,
    save_path: Path = None,
    max_words: int = None,
    window_size: int = 8,
    z_threshold: float = 2.0
):
    """
    Plot word durations and gaps as a sequence graph with duration analysis.
    
    This visualization shows:
    - Word durations as bars (color-coded by z-score)
    - Moving average line
    - Z-scores
    - Gaps between words
    - Sentence boundaries (if sentences provided)
    
    Args:
        words: List of word dictionaries with 'start', 'end', 'text' keys
        sentences: Optional list of sentence dictionaries (for highlighting boundaries)
        gaps: Optional pre-calculated gaps (will calculate if not provided)
        save_path: Optional path to save the figure
        max_words: Optional limit on number of words to display (for readability)
        window_size: Size of moving window for statistics
        z_threshold: Z-score threshold for highlighting
    """
    if not words:
        print("No words to plot")
        return
    
    # Limit words if specified
    if max_words and len(words) > max_words:
        words = words[:max_words]
        print(f"  Plotting first {max_words} words (out of {len(words)})")
    
    # Calculate word durations and positions
    word_durations = []
    word_starts = []
    word_texts = []
    
    for word in words:
        duration = word['end'] - word['start']
        word_durations.append(duration)
        word_starts.append(word['start'])
        word_texts.append(word.get('text', ''))
    
    # Calculate moving statistics
    moving_stats = calculate_moving_stats(words, window_size)
    moving_avgs = [s['moving_avg'] for s in moving_stats]
    z_scores = [s['z_score'] for s in moving_stats]
    
    # Calculate gaps if not provided
    if gaps is None:
        gaps = calculate_word_gaps(words)
    
    # Limit gaps to match words
    if len(gaps) >= len(words):
        gaps = gaps[:len(words)-1] if len(words) > 1 else []
    
    # Create figure with 3 subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
    
    # Plot 1: Word durations as bars (color-coded by z-score)
    word_indices = list(range(len(words)))
    word_colors = []
    for z in z_scores:
        if z >= 2.5:
            word_colors.append('red')  # Strong boundary
        elif z >= 1.5:
            word_colors.append('orange')  # Potential boundary
        else:
            word_colors.append('steelblue')  # Normal
    
    # Plot word durations
    ax1.bar(word_indices, word_durations, color=word_colors, alpha=0.7, edgecolor='black', linewidth=0.5)
    ax1.set_ylabel('Word Duration (ms)', fontsize=12, fontweight='bold')
    ax1.set_title('Word Duration Sequence with Moving Average', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # Plot moving average line
    if len(moving_avgs) > 0:
        ax1.plot(word_indices, moving_avgs, color='green', linestyle='--', 
                linewidth=2, label=f'Moving Avg (window={window_size})', marker='o', markersize=3)
        ax1.legend(loc='upper right')
    
    # Add z-score annotations for high-scoring words
    for i, (idx, z) in enumerate(zip(word_indices, z_scores)):
        if z >= 1.5:
            ax1.text(idx, word_durations[i], f'z={z:.1f}', 
                    ha='center', va='bottom', fontsize=8, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    # Add color legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='steelblue', label='Normal (z < 1.5)'),
        Patch(facecolor='orange', label='Potential Boundary (1.5 ≤ z < 2.5)'),
        Patch(facecolor='red', label='Strong Boundary (z ≥ 2.5)')
    ]
    ax1.legend(handles=legend_elements, loc='upper left')
    
    # Plot 2: Z-scores
    ax2.plot(word_indices, z_scores, color='purple', linewidth=2, marker='o', markersize=4)
    ax2.axhline(y=z_threshold, color='red', linestyle='--', linewidth=2, 
               label=f'Threshold (z={z_threshold})')
    ax2.axhline(y=1.5, color='orange', linestyle='--', linewidth=1, alpha=0.5)
    ax2.axhline(y=2.5, color='red', linestyle='--', linewidth=1, alpha=0.5)
    ax2.fill_between(word_indices, z_threshold, max(z_scores) if z_scores else z_threshold, 
                     alpha=0.2, color='red', label='Anomaly Region')
    ax2.set_ylabel('Z-Score', fontsize=12, fontweight='bold')
    ax2.set_title('Z-Score Sequence (Duration Anomalies)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    # Plot 3: Gaps between words
    if gaps:
        gap_indices = list(range(len(gaps)))
        gap_colors = ['green' if g == 0 else 'red' if g >= 1000 else 'orange' for g in gaps]
        
        ax3.bar(gap_indices, gaps, color=gap_colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax3.set_xlabel('Word Index', fontsize=12, fontweight='bold')
        ax3.set_ylabel('Gap Duration (ms)', fontsize=12, fontweight='bold')
        ax3.set_title('Gaps Between Consecutive Words', fontsize=14, fontweight='bold')
        ax3.grid(True, alpha=0.3, axis='y')
    
    # Mark sentence boundaries
    if sentences:
        word_idx = 0
        for sent_idx, sentence in enumerate(sentences):
            sentence_word_count = len(sentence.get('words', []))
            boundary_idx = word_idx + sentence_word_count - 1
            
            if boundary_idx < len(words):
                # Mark on all plots
                ax1.axvline(x=boundary_idx + 0.5, color='red', linestyle='-', linewidth=2, alpha=0.5)
                ax2.axvline(x=boundary_idx + 0.5, color='red', linestyle='-', linewidth=2, alpha=0.5)
                if boundary_idx < len(gaps):
                    ax3.axvline(x=boundary_idx, color='red', linestyle='-', linewidth=2, alpha=0.5)
            
            word_idx += sentence_word_count
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  Saved sequence plot to: {save_path}")
    else:
        plt.show()
    
    plt.close()


def plot_timeline_sequence(
    words: List[Dict],
    sentences: List[Dict] = None,
    save_path: Path = None,
    max_duration: float = None,
    window_size: int = 8,
    z_threshold: float = 2.0
):
    """
    Plot words and gaps on a timeline (time-based x-axis) with duration analysis.
    
    This shows the actual temporal distribution of words and gaps, with moving average
    and z-score analysis for detecting sentence boundaries.
    
    Args:
        words: List of word dictionaries
        sentences: Optional list of sentence dictionaries
        save_path: Optional path to save the figure
        max_duration: Optional maximum duration to display (in ms)
        window_size: Size of moving window for statistics
        z_threshold: Z-score threshold for highlighting
    """
    if not words:
        print("No words to plot")
        return
    
    # Calculate word positions and durations
    word_starts = [w['start'] for w in words]
    word_ends = [w['end'] for w in words]
    word_durations = [e - s for s, e in zip(word_starts, word_ends)]
    
    # Calculate moving statistics
    moving_stats = calculate_moving_stats(words, window_size)
    moving_avgs = [s['moving_avg'] for s in moving_stats]
    z_scores = [s['z_score'] for s in moving_stats]
    
    # Calculate gaps
    gaps = calculate_word_gaps(words)
    gap_starts = []
    gap_durations = []
    for i in range(len(gaps)):
        gap_starts.append(word_ends[i])
        gap_durations.append(gaps[i])
    
    # Limit duration if specified
    if max_duration:
        words_to_show = [i for i, start in enumerate(word_starts) if start < max_duration]
        if words_to_show:
            words = [words[i] for i in words_to_show]
            word_starts = [word_starts[i] for i in words_to_show]
            word_ends = [word_ends[i] for i in words_to_show]
            word_durations = [word_durations[i] for i in words_to_show]
            moving_avgs = [moving_avgs[i] for i in words_to_show]
            z_scores = [z_scores[i] for i in words_to_show]
            gaps = gaps[:len(words)-1] if len(words) > 1 else []
            gap_starts = gap_starts[:len(gaps)]
            gap_durations = gap_durations[:len(gaps)]
    
    # Create figure with 3 subplots
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True)
    
    # Plot 1: Word timeline with color coding by z-score
    y_positions = [1] * len(words)
    word_colors = []
    for z in z_scores:
        if z >= 2.5:
            word_colors.append('red')  # Strong boundary
        elif z >= 1.5:
            word_colors.append('orange')  # Potential boundary
        else:
            word_colors.append('steelblue')  # Normal
    
    for i, (start, duration) in enumerate(zip(word_starts, word_durations)):
        ax1.barh(y_positions[i], duration, left=start, height=0.8, 
                color=word_colors[i], alpha=0.7, edgecolor='black', linewidth=0.5)
        
        # Add z-score annotation for high-scoring words
        if z_scores[i] >= 1.5:
            mid_time = start + duration / 2
            ax1.text(mid_time, y_positions[i], f'z={z_scores[i]:.1f}', 
                    ha='center', va='center', fontsize=8, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    
    # Plot moving average line
    if len(moving_avgs) > 0:
        # Create time points for moving average (use word start times)
        ax1.plot(word_starts, moving_avgs, color='green', linestyle='--', 
                linewidth=2, label=f'Moving Avg (window={window_size})', alpha=0.7)
        ax1.legend(loc='upper right')
    
    # Mark sentence boundaries
    if sentences:
        word_idx = 0
        for sentence in sentences:
            sentence_words = sentence.get('words', [])
            if sentence_words:
                sentence_end = sentence_words[-1]['end']
                ax1.axvline(x=sentence_end, color='red', linestyle='-', linewidth=2, alpha=0.7)
            word_idx += len(sentence_words)
    
    ax1.set_ylabel('Words', fontsize=12, fontweight='bold')
    ax1.set_title('Word Timeline with Duration Analysis (Time-based)', fontsize=14, fontweight='bold')
    ax1.set_yticks([])
    ax1.grid(True, alpha=0.3, axis='x')
    
    # Add color legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='steelblue', label='Normal (z < 1.5)'),
        Patch(facecolor='orange', label='Potential Boundary (1.5 ≤ z < 2.5)'),
        Patch(facecolor='red', label='Strong Boundary (z ≥ 2.5)')
    ]
    ax1.legend(handles=legend_elements, loc='upper left')
    
    # Plot 2: Z-scores over time
    ax2.plot(word_starts, z_scores, color='purple', linewidth=2, marker='o', markersize=3)
    ax2.axhline(y=z_threshold, color='red', linestyle='--', linewidth=2, 
               label=f'Threshold (z={z_threshold})')
    ax2.axhline(y=1.5, color='orange', linestyle='--', linewidth=1, alpha=0.5)
    ax2.axhline(y=2.5, color='red', linestyle='--', linewidth=1, alpha=0.5)
    ax2.fill_between(word_starts, z_threshold, max(z_scores) if z_scores else z_threshold, 
                     alpha=0.2, color='red', label='Anomaly Region')
    ax2.set_ylabel('Z-Score', fontsize=12, fontweight='bold')
    ax2.set_title('Z-Score Timeline (Duration Anomalies)', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    # Plot 3: Gap timeline
    if gaps:
        gap_y_positions = [1] * len(gaps)
        gap_colors = ['green' if g == 0 else 'red' if g >= 1000 else 'orange' for g in gap_durations]
        
        for i, (start, duration) in enumerate(zip(gap_starts, gap_durations)):
            if duration > 0:  # Only plot non-zero gaps
                ax3.barh(gap_y_positions[i], duration, left=start, height=0.8,
                        color=gap_colors[i], alpha=0.7, edgecolor='black', linewidth=0.5)
    
    ax3.set_xlabel('Time (ms)', fontsize=12, fontweight='bold')
    ax3.set_ylabel('Gaps', fontsize=12, fontweight='bold')
    ax3.set_title('Gap Timeline (Time-based)', fontsize=14, fontweight='bold')
    ax3.set_yticks([])
    ax3.grid(True, alpha=0.3, axis='x')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  Saved timeline plot to: {save_path}")
    else:
        plt.show()
    
    plt.close()


def analyze_transcript(transcript_path: Path, output_dir: Path = None):
    """
    Analyze word gaps in transcript and generate histograms.
    
    Args:
        transcript_path: Path to transcript JSON file
        output_dir: Directory to save histograms. If None, displays them.
    """
    print(f"Loading transcript: {transcript_path}")
    transcript = load_transcript(transcript_path)
    
    # Extract words array
    words = transcript.get('words', [])
    if not words:
        # Try alternative location
        words = transcript.get('json_response', {}).get('words', [])
    
    if not words:
        raise ValueError("No words array found in transcript")
    
    print(f"  Found {len(words)} words")
    
    # Calculate gaps
    gaps = calculate_word_gaps(words)
    print(f"  Calculated {len(gaps)} gaps")
    
    # Calculate word durations
    durations = calculate_word_durations(words)
    print(f"  Calculated {len(durations)} word durations")
    
    # Calculate statistics
    print("\n=== Gap Statistics (All Gaps) ===")
    gap_stats = calculate_statistics(gaps, "gaps")
    for key, value in gap_stats.items():
        if key != 'percentiles':
            print(f"  {key}: {value:.2f} ms")
    
    print("\n=== Gap Percentiles (All Gaps) ===")
    for percentile, value in gap_stats['percentiles'].items():
        print(f"  {percentile}: {value:.2f} ms")
    
    # Analyze non-zero gaps separately (more informative for sentence boundaries)
    non_zero_gaps = [g for g in gaps if g > 0]
    zero_count = len(gaps) - len(non_zero_gaps)
    
    print("\n=== Gap Distribution ===")
    print(f"  Zero gaps: {zero_count} ({zero_count/len(gaps)*100:.1f}%)")
    print(f"  Non-zero gaps: {len(non_zero_gaps)} ({len(non_zero_gaps)/len(gaps)*100:.1f}%)")
    
    non_zero_stats = {}
    if non_zero_gaps:
        print("\n=== Non-Zero Gap Statistics ===")
        non_zero_stats = calculate_statistics(non_zero_gaps, "non_zero_gaps")
        for key, value in non_zero_stats.items():
            if key != 'percentiles':
                print(f"  {key}: {value:.2f} ms")
        
        print("\n=== Non-Zero Gap Percentiles ===")
        for percentile, value in non_zero_stats['percentiles'].items():
            print(f"  {percentile}: {value:.2f} ms")
    
    print("\n=== Word Duration Statistics ===")
    duration_stats = calculate_statistics(durations, "durations")
    for key, value in duration_stats.items():
        if key != 'percentiles':
            print(f"  {key}: {value:.2f} ms")
    
    # Generate output directory if specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        base_name = transcript_path.stem
    
    # Plot 1: Gap histogram (full range)
    title1 = f"Word Gap Distribution (Full Range)\n{transcript_path.stem}"
    path1 = output_dir / f"{base_name}_gaps_full.png" if output_dir else None
    plot_histogram(
        gaps,
        title1,
        "Gap Duration (ms)",
        "Number of Gaps",
        bins=100,
        save_path=path1
    )
    
    # Plot 2: Gap histogram (zoomed to 0-2000ms for better visibility)
    title2 = f"Word Gap Distribution (0-2000ms)\n{transcript_path.stem}"
    path2 = output_dir / f"{base_name}_gaps_zoomed.png" if output_dir else None
    plot_histogram(
        gaps,
        title2,
        "Gap Duration (ms)",
        "Number of Gaps",
        bins=100,
        xlim=(0, 2000),
        save_path=path2
    )
    
    # Plot 3: Gap histogram (log scale)
    title3 = f"Word Gap Distribution (Log Scale)\n{transcript_path.stem}"
    path3 = output_dir / f"{base_name}_gaps_log.png" if output_dir else None
    plot_log_histogram(
        gaps,
        title3,
        "Gap Duration (ms, log scale)",
        "Number of Gaps",
        bins=100,
        save_path=path3
    )
    
    # Plot 4: Word duration histogram
    title4 = f"Word Duration Distribution\n{transcript_path.stem}"
    path4 = output_dir / f"{base_name}_durations.png" if output_dir else None
    plot_histogram(
        durations,
        title4,
        "Word Duration (ms)",
        "Number of Words",
        bins=50,
        save_path=path4
    )
    
    # Plot 5: Non-zero gaps histogram (if any exist)
    if non_zero_gaps:
        title5 = f"Non-Zero Gap Distribution\n{transcript_path.stem}"
        path5 = output_dir / f"{base_name}_gaps_nonzero.png" if output_dir else None
        plot_histogram(
            non_zero_gaps,
            title5,
            "Gap Duration (ms)",
            "Number of Gaps",
            bins=50,
            save_path=path5
        )
    
    # Suggest threshold based on statistics
    print("\n=== Suggested Thresholds for Sentence Segmentation ===")
    
    # Use non-zero gap statistics if available, otherwise use all gaps
    if non_zero_gaps:
        stats_for_threshold = non_zero_stats
        print("  (Using non-zero gap statistics)")
    else:
        stats_for_threshold = gap_stats
        print("  (Using all gap statistics)")
    
    stats_for_threshold['percentiles']['p95']
    p99 = stats_for_threshold['percentiles']['p99']
    mean = stats_for_threshold['mean']
    stats_for_threshold['median']
    std = stats_for_threshold['std']
    
    # Conservative threshold (catches most sentence boundaries)
    # Use P90 of non-zero gaps or fixed value
    if non_zero_gaps:
        conservative = stats_for_threshold['percentiles']['p90']
    else:
        conservative = 500  # Fallback if all gaps are zero
    
    # Moderate threshold (balances precision and recall)
    moderate = p99 if p99 > 0 else 1000
    
    # Aggressive threshold (only very clear boundaries)
    aggressive = mean + 2 * std if std > 0 else 2000
    
    print(f"  Conservative (P90 of non-zero): {conservative:.1f} ms - catches most sentence boundaries")
    print(f"  Moderate (P99): {moderate:.1f} ms - balances precision/recall")
    print(f"  Aggressive (Mean + 2*Std): {aggressive:.1f} ms - only very clear boundaries")
    
    # Count gaps above each threshold
    gaps_array = np.array(gaps)
    conservative_count = np.sum(gaps_array >= conservative)
    moderate_count = np.sum(gaps_array >= moderate)
    aggressive_count = np.sum(gaps_array >= aggressive)
    
    print(f"\n  Gaps >= Conservative threshold: {conservative_count} ({conservative_count/len(gaps)*100:.1f}%)")
    print(f"  Gaps >= Moderate threshold: {moderate_count} ({moderate_count/len(gaps)*100:.1f}%)")
    print(f"  Gaps >= Aggressive threshold: {aggressive_count} ({aggressive_count/len(gaps)*100:.1f}%)")
    
    # Show some example gaps above threshold
    if moderate_count > 0:
        print(f"\n=== Example Large Gaps (>= {moderate:.0f}ms) ===")
        large_gaps = [(i, g) for i, g in enumerate(gaps) if g >= moderate]
        large_gaps.sort(key=lambda x: x[1], reverse=True)
        for idx, (gap_idx, gap_val) in enumerate(large_gaps[:5]):  # Show top 5
            word_before = words[gap_idx]
            word_after = words[gap_idx + 1] if gap_idx + 1 < len(words) else None
            print(f"  Gap #{gap_idx}: {gap_val:.0f}ms")
            print(f"    Before: '{word_before['text']}' (ends at {word_before['end']}ms)")
            if word_after:
                print(f"    After: '{word_after['text']}' (starts at {word_after['start']}ms)")
    
    return {
        'gaps': gaps,
        'non_zero_gaps': non_zero_gaps if non_zero_gaps else [],
        'durations': durations,
        'gap_stats': gap_stats,
        'non_zero_gap_stats': non_zero_stats if non_zero_gaps else {},
        'duration_stats': duration_stats,
        'suggested_thresholds': {
            'conservative': conservative,
            'moderate': moderate,
            'aggressive': aggressive
        }
    }


def calculate_speaker_statistics(words: List[Dict]) -> Dict[str, Dict]:
    """
    Calculate gap statistics per speaker.
    
    Args:
        words: List of word dictionaries with 'start', 'end', and optionally 'speaker' keys
        
    Returns:
        Dictionary mapping speaker IDs to their gap statistics
    """
    speaker_gaps = {}
    
    # Group gaps by speaker
    for i in range(len(words) - 1):
        current_word = words[i]
        next_word = words[i + 1]
        
        # Get speaker IDs (handle None case)
        current_speaker = current_word.get('speaker', 'unknown')
        next_speaker = next_word.get('speaker', 'unknown')
        
        # Only consider gaps within the same speaker's speech
        # (gaps between speakers are definitely sentence boundaries)
        if current_speaker == next_speaker and current_speaker is not None:
            speaker_id = str(current_speaker)
            if speaker_id not in speaker_gaps:
                speaker_gaps[speaker_id] = []
            
            gap = next_word['start'] - current_word['end']
            speaker_gaps[speaker_id].append(gap)
    
    # Calculate statistics for each speaker
    speaker_stats = {}
    for speaker_id, gaps in speaker_gaps.items():
        if gaps:
            non_zero_gaps = [g for g in gaps if g > 0]
            all_stats = calculate_statistics(gaps, f"speaker_{speaker_id}")
            non_zero_stats = calculate_statistics(non_zero_gaps, f"speaker_{speaker_id}_non_zero") if non_zero_gaps else {}
            
            speaker_stats[speaker_id] = {
                'all_gaps': gaps,
                'non_zero_gaps': non_zero_gaps,
                'all_stats': all_stats,
                'non_zero_stats': non_zero_stats,
                'threshold': _calculate_adaptive_threshold(all_stats, non_zero_stats, non_zero_gaps)
            }
    
    return speaker_stats


def _calculate_adaptive_threshold(
    all_stats: Dict,
    non_zero_stats: Dict,
    non_zero_gaps: List[float]
) -> float:
    """
    Calculate adaptive threshold for sentence segmentation.
    
    Uses the minimum non-zero gap as a baseline, with fallbacks.
    
    Args:
        all_stats: Statistics for all gaps
        non_zero_stats: Statistics for non-zero gaps
        non_zero_gaps: List of non-zero gap values
        
    Returns:
        Suggested threshold in milliseconds
    """
    if non_zero_gaps:
        # Use minimum non-zero gap as baseline (most conservative)
        min_non_zero = min(non_zero_gaps)
        # Use P25 of non-zero gaps as threshold (catches most sentence boundaries)
        if non_zero_stats and 'percentiles' in non_zero_stats:
            p25 = non_zero_stats['percentiles'].get('p25', min_non_zero)
            # Use the smaller of min_non_zero * 1.5 or p25, but at least 500ms
            threshold = max(min(min_non_zero * 1.5, p25), 500)
        else:
            threshold = max(min_non_zero, 500)
    else:
        # Fallback if no non-zero gaps
        threshold = 1000
    
    return threshold


def segment_words_by_duration(
    words: List[Dict],
    window_size: int = 8,
    z_threshold: float = 2.0,
    min_sentence_length: int = 3,
    min_words_before: int = 3,
    require_longer_than_neighbors: bool = True,
    neighbor_ratio_threshold: float = 1.5
) -> List[Dict]:
    """
    Segment words into sentences based on duration anomalies (moving average + z-score).
    
    Detects words that are significantly longer than expected AND longer than both
    previous and next words, which likely contain pauses indicating sentence boundaries.
    
    Args:
        words: List of word dictionaries with 'start', 'end', and optionally 'speaker' keys
        window_size: Size of moving window for calculating statistics
        z_threshold: Z-score threshold for detecting anomalies (default: 2.0)
        min_sentence_length: Minimum number of words per sentence
        min_words_before: Minimum words before first boundary can be detected
        require_longer_than_neighbors: If True, word must be longer than both previous and next words
        neighbor_ratio_threshold: Ratio threshold for neighbor comparison (default: 1.5x)
        
    Returns:
        List of sentence dictionaries, each containing:
        - 'text': Sentence text
        - 'words': List of word dictionaries in this sentence
        - 'start': Start time of first word (ms)
        - 'end': End time of last word (ms)
        - 'duration': Total duration (ms)
        - 'confidence': Average confidence of words
        - 'speaker': Speaker ID if available
    """
    if not words:
        return []
    
    # Detect anomalies
    anomalies = detect_duration_anomalies(
        words,
        window_size=window_size,
        z_threshold=z_threshold,
        min_words_before=min_words_before,
        require_longer_than_neighbors=require_longer_than_neighbors,
        neighbor_ratio_threshold=neighbor_ratio_threshold
    )
    
    # Get indices of boundaries (anomalies mark the END of a sentence)
    boundary_indices = {a['word_idx'] for a in anomalies}
    
    # Build sentences
    sentences = []
    current_sentence_words = []
    
    for i, word in enumerate(words):
        current_sentence_words.append(word)
        
        # Check if this is a boundary (end of sentence)
        is_boundary = i in boundary_indices
        is_last_word = i == len(words) - 1
        
        # Finalize sentence if:
        # 1. We hit a boundary AND have enough words, OR
        # 2. This is the last word
        if (is_boundary and len(current_sentence_words) >= min_sentence_length) or is_last_word:
            if current_sentence_words:
                sentence = _create_sentence_from_words(current_sentence_words)
                sentences.append(sentence)
                current_sentence_words = []
    
    # Handle any remaining words
    if current_sentence_words:
        if len(sentences) > 0:
            # Merge with last sentence if too short
            if len(current_sentence_words) < min_sentence_length:
                sentences[-1]['words'].extend(current_sentence_words)
                sentences[-1] = _create_sentence_from_words(sentences[-1]['words'])
            else:
                sentence = _create_sentence_from_words(current_sentence_words)
                sentences.append(sentence)
        else:
            sentence = _create_sentence_from_words(current_sentence_words)
            sentences.append(sentence)
    
    return sentences


def segment_words_into_sentences(
    words: List[Dict],
    threshold: float = None,
    speaker_stats: Dict[str, Dict] = None,
    use_speaker_adaptive: bool = True,
    method: str = 'gap'
) -> List[Dict]:
    """
    Segment words into sentences based on timing gaps or duration analysis.
    
    Args:
        words: List of word dictionaries with 'start', 'end', and optionally 'speaker' keys
        threshold: Fixed threshold in milliseconds (for gap method). If None, will use adaptive threshold.
        speaker_stats: Pre-calculated speaker statistics (optional, for gap method)
        use_speaker_adaptive: If True, use speaker-specific thresholds when available (for gap method)
        method: Segmentation method - 'gap' (gap-based) or 'duration' (duration-based)
        
    Returns:
        List of sentence dictionaries, each containing:
        - 'text': Sentence text
        - 'words': List of word dictionaries in this sentence
        - 'start': Start time of first word (ms)
        - 'end': End time of last word (ms)
        - 'duration': Total duration (ms)
        - 'confidence': Average confidence of words
        - 'speaker': Speaker ID if available
    """
    if not words:
        return []
    
    if method == 'duration':
        # Use duration-based segmentation
        return segment_words_by_duration(words)
    else:
        # Use gap-based segmentation (original method)
        return _segment_words_by_gaps(words, threshold, speaker_stats, use_speaker_adaptive)


def _segment_words_by_gaps(
    words: List[Dict],
    threshold: float = None,
    speaker_stats: Dict[str, Dict] = None,
    use_speaker_adaptive: bool = True
) -> List[Dict]:
    """
    Segment words into sentences based on timing gaps (original implementation).
    
    This is the original gap-based method, extracted for clarity.
    
    Args:
        words: List of word dictionaries with 'start', 'end', and optionally 'speaker' keys
        threshold: Fixed threshold in milliseconds. If None, will use adaptive threshold.
        speaker_stats: Pre-calculated speaker statistics (optional, will calculate if not provided)
        use_speaker_adaptive: If True, use speaker-specific thresholds when available
        
    Returns:
        List of sentence dictionaries
    """
    if not words:
        return []
    
    # Calculate speaker statistics if not provided and adaptive mode is enabled
    if use_speaker_adaptive and speaker_stats is None:
        speaker_stats = calculate_speaker_statistics(words)
    
    # Use default threshold if not provided
    if threshold is None:
        # Calculate global statistics for fallback
        gaps = calculate_word_gaps(words)
        non_zero_gaps = [g for g in gaps if g > 0]
        all_stats = calculate_statistics(gaps, "global")
        non_zero_stats = calculate_statistics(non_zero_gaps, "global_non_zero") if non_zero_gaps else {}
        threshold = _calculate_adaptive_threshold(all_stats, non_zero_stats, non_zero_gaps)
    
    sentences = []
    current_sentence_words = []
    
    for i, word in enumerate(words):
        current_sentence_words.append(word)
        
        # Check if this is the last word
        if i == len(words) - 1:
            # End of transcript, finalize current sentence
            if current_sentence_words:
                sentence = _create_sentence_from_words(current_sentence_words)
                sentences.append(sentence)
            break
        
        # Calculate gap to next word
        next_word = words[i + 1]
        gap = next_word['start'] - word['end']
        
        # Determine threshold to use
        effective_threshold = threshold
        
        if use_speaker_adaptive and speaker_stats:
            current_speaker = word.get('speaker')
            next_speaker = next_word.get('speaker')
            
            # If both words have the same speaker, use speaker-specific threshold
            if current_speaker == next_speaker and current_speaker is not None:
                speaker_id = str(current_speaker)
                if speaker_id in speaker_stats:
                    effective_threshold = speaker_stats[speaker_id]['threshold']
            # If different speakers, always treat as sentence boundary
            elif current_speaker != next_speaker:
                effective_threshold = 0  # Always break between speakers
        
        # Check if gap indicates sentence boundary
        if gap >= effective_threshold:
            # Finalize current sentence
            if current_sentence_words:
                sentence = _create_sentence_from_words(current_sentence_words)
                sentences.append(sentence)
                current_sentence_words = []
    
    return sentences


def _create_sentence_from_words(words: List[Dict]) -> Dict:
    """Create a sentence dictionary from a list of words."""
    if not words:
        return {}
    
    # Extract text
    text = "".join([w['text'] for w in words])
    
    # Calculate timing
    start = words[0]['start']
    end = words[-1]['end']
    duration = end - start
    
    # Calculate average confidence
    confidences = [w.get('confidence', 0.0) for w in words if w.get('confidence') is not None]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    
    # Get speaker (use first word's speaker, or None if inconsistent)
    speaker = words[0].get('speaker')
    if speaker is not None:
        # Check if all words have the same speaker
        for word in words[1:]:
            if word.get('speaker') != speaker:
                speaker = None  # Mixed speakers
                break
    
    return {
        'text': text,
        'words': words,
        'start': start,
        'end': end,
        'duration': duration,
        'confidence': avg_confidence,
        'speaker': speaker,
        'word_count': len(words)
    }


def generate_sentences_from_transcript(
    transcript_path: Path,
    threshold: float = None,
    use_speaker_adaptive: bool = True,
    output_path: Path = None,
    method: str = 'duration',
    window_size: int = 8,
    z_threshold: float = 2.0,
    require_longer_than_neighbors: bool = True,
    neighbor_ratio_threshold: float = 1.5
) -> List[Dict]:
    """
    Load transcript and generate sentences using gap-based or duration-based segmentation.
    
    Args:
        transcript_path: Path to transcript JSON file
        threshold: Fixed threshold in milliseconds (for gap method). If None, uses adaptive threshold.
        use_speaker_adaptive: If True, adapts threshold per speaker (for gap method)
        output_path: Optional path to save sentences JSON file
        method: Segmentation method - 'gap' (gap-based) or 'duration' (duration-based, default)
        window_size: Size of moving window for duration method (default: 8)
        z_threshold: Z-score threshold for duration method (default: 2.0)
        require_longer_than_neighbors: If True, word must be longer than both previous and next words (default: True)
        neighbor_ratio_threshold: Ratio threshold for neighbor comparison (default: 1.5x)
        
    Returns:
        List of sentence dictionaries
    """
    print(f"Loading transcript: {transcript_path}")
    transcript = load_transcript(transcript_path)
    
    # Extract words array
    words = transcript.get('words', [])
    if not words:
        words = transcript.get('json_response', {}).get('words', [])
    
    if not words:
        raise ValueError("No words array found in transcript")
    
    print(f"  Found {len(words)} words")
    print(f"  Using method: {method}")
    
    # Calculate speaker statistics if gap method and adaptive mode is enabled
    speaker_stats = None
    if method == 'gap' and use_speaker_adaptive:
        print("  Calculating speaker-specific statistics...")
        speaker_stats = calculate_speaker_statistics(words)
        if speaker_stats:
            print(f"  Found {len(speaker_stats)} speaker(s)")
            for speaker_id, stats in speaker_stats.items():
                threshold_val = stats['threshold']
                print(f"    Speaker {speaker_id}: threshold = {threshold_val:.1f}ms")
        else:
            print("  No speaker labels found, using global statistics")
    
    # Generate sentences
    print("  Segmenting words into sentences...")
    if method == 'duration':
        if require_longer_than_neighbors:
            print(f"  Requiring words to be {neighbor_ratio_threshold}x longer than both neighbors")
        sentences = segment_words_by_duration(
            words,
            window_size=window_size,
            z_threshold=z_threshold,
            require_longer_than_neighbors=require_longer_than_neighbors,
            neighbor_ratio_threshold=neighbor_ratio_threshold
        )
    else:
        sentences = segment_words_into_sentences(
            words,
            threshold=threshold,
            speaker_stats=speaker_stats,
            use_speaker_adaptive=use_speaker_adaptive,
            method='gap'
        )
    
    print(f"  Generated {len(sentences)} sentences")
    
    # Calculate summary statistics
    if sentences:
        avg_sentence_length = sum(len(s['words']) for s in sentences) / len(sentences)
        avg_duration = sum(s['duration'] for s in sentences) / len(sentences)
        print(f"  Average sentence length: {avg_sentence_length:.1f} words")
        print(f"  Average sentence duration: {avg_duration:.1f}ms ({avg_duration/1000:.2f}s)")
    
    # Generate sequence visualizations
    if output_path:
        output_dir = Path(output_path).parent
        base_name = Path(output_path).stem
        
        # Calculate gaps for visualization
        gaps = calculate_word_gaps(words)
        
        # Plot word sequence
        seq_path = output_dir / f"{base_name}_sequence.png"
        print("  Generating sequence plot...")
        plot_word_sequence(words, sentences, gaps, save_path=seq_path, max_words=255,
                          window_size=window_size, z_threshold=z_threshold)
        
        # Plot timeline
        timeline_path = output_dir / f"{base_name}_timeline.png"
        print("  Generating timeline plot...")
        plot_timeline_sequence(words, sentences, save_path=timeline_path,
                              window_size=window_size, z_threshold=z_threshold)
    
    # Save to file if output path provided
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        output_data = {
            'source_transcript': str(transcript_path),
            'total_words': len(words),
            'total_sentences': len(sentences),
            'method': method,
            'threshold_used': threshold if threshold else 'adaptive' if method == 'gap' else None,
            'window_size': window_size if method == 'duration' else None,
            'z_threshold': z_threshold if method == 'duration' else None,
            'require_longer_than_neighbors': require_longer_than_neighbors if method == 'duration' else None,
            'neighbor_ratio_threshold': neighbor_ratio_threshold if method == 'duration' else None,
            'use_speaker_adaptive': use_speaker_adaptive if method == 'gap' else None,
            'speaker_stats': {k: {'threshold': v['threshold']} for k, v in (speaker_stats or {}).items()} if speaker_stats else {},
            'sentences': sentences
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"  Saved sentences to: {output_path}")
    
    return sentences


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="Analyze word gaps and generate sentences from transcript",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze gaps and generate histograms
  python analyze_word_gaps.py transcript.json
  
  # Generate sentences with default adaptive threshold
  python analyze_word_gaps.py transcript.json --generate-sentences
  
  # Generate sentences with fixed threshold
  python analyze_word_gaps.py transcript.json --generate-sentences --threshold 1000
  
  # Generate sentences without speaker adaptation
  python analyze_word_gaps.py transcript.json --generate-sentences --no-speaker-adaptive
        """
    )
    
    parser.add_argument(
        'transcript_path',
        nargs='?',
        type=str,
        help='Path to transcript JSON file'
    )
    parser.add_argument(
        '--generate-sentences',
        action='store_true',
        help='Generate sentences from transcript using segmentation'
    )
    parser.add_argument(
        '--method',
        type=str,
        choices=['gap', 'duration'],
        default='duration',
        help='Segmentation method: gap (gap-based) or duration (duration-based, default)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=None,
        help='Fixed threshold in milliseconds for gap-based segmentation (default: adaptive)'
    )
    parser.add_argument(
        '--window-size',
        type=int,
        default=8,
        help='Moving window size for duration-based method (default: 8)'
    )
    parser.add_argument(
        '--z-threshold',
        type=float,
        default=2.0,
        help='Z-score threshold for duration-based method (default: 2.0)'
    )
    parser.add_argument(
        '--no-neighbor-check',
        action='store_true',
        help='Disable requirement that word must be longer than both neighbors (duration method only)'
    )
    parser.add_argument(
        '--neighbor-ratio',
        type=float,
        default=1.5,
        help='Ratio threshold for neighbor comparison: word must be N times longer than neighbors (default: 1.5)'
    )
    parser.add_argument(
        '--no-speaker-adaptive',
        action='store_true',
        help='Disable speaker-specific threshold adaptation (gap method only)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Output path for sentences JSON (only used with --generate-sentences)'
    )
    parser.add_argument(
        '--plot-sequence',
        action='store_true',
        help='Generate sequence visualization plots (word durations and gaps)'
    )
    
    args = parser.parse_args()
    
    # Default transcript path
    default_transcript = Path(__file__).parent.parent / "data" / "test_transcript" / "shortmp3_transcript.json"
    
    if args.transcript_path:
        transcript_path = Path(args.transcript_path)
    else:
        transcript_path = default_transcript
    
    if not transcript_path.exists():
        print(f"Error: Transcript file not found: {transcript_path}")
        print("\nUsage: python analyze_word_gaps.py [transcript_path] [options]")
        print(f"Default: {default_transcript}")
        parser.print_help()
        sys.exit(1)
    
    # Output directory for histograms
    output_dir = Path(__file__).parent.parent / "data" / "test_transcript" / "analysis"
    
    if args.generate_sentences or args.plot_sequence:
        # Generate sentences mode
        print("=" * 60)
        print("Sentence Generation from Transcript")
        print("=" * 60)
        
        # Determine output path
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = output_dir.parent / f"{transcript_path.stem}_sentences.json"
        
        try:
            sentences = generate_sentences_from_transcript(
                transcript_path,
                threshold=args.threshold,
                use_speaker_adaptive=not args.no_speaker_adaptive,
                output_path=output_path if args.generate_sentences else None,
                method=args.method,
                window_size=args.window_size,
                z_threshold=args.z_threshold,
                require_longer_than_neighbors=not args.no_neighbor_check,
                neighbor_ratio_threshold=args.neighbor_ratio
            )
            
            # Generate sequence plots if requested
            if args.plot_sequence:
                print("\n" + "=" * 60)
                print("Generating Sequence Visualizations")
                print("=" * 60)
                
                # Load words from transcript
                transcript = load_transcript(transcript_path)
                words = transcript.get('words', [])
                if not words:
                    words = transcript.get('json_response', {}).get('words', [])
                
                gaps = calculate_word_gaps(words)
                
                # Generate plots
                base_name = transcript_path.stem
                seq_path = output_dir / f"{base_name}_sequence.png"
                timeline_path = output_dir / f"{base_name}_timeline.png"
                
                print(f"  Generating sequence plot: {seq_path}")
                plot_word_sequence(words, sentences, gaps, save_path=seq_path, max_words=255,
                                  window_size=args.window_size, z_threshold=args.z_threshold)
                
                print(f"  Generating timeline plot: {timeline_path}")
                plot_timeline_sequence(words, sentences, save_path=timeline_path,
                                      window_size=args.window_size, z_threshold=args.z_threshold)
                
                print("\nSequence visualizations completed!")
            
            if args.generate_sentences:
                print("\n" + "=" * 60)
                print("Sentence generation completed successfully!")
                print("=" * 60)
                print("\nFirst 3 sentences preview:")
                for i, sentence in enumerate(sentences[:3], 1):
                    print(f"\n  Sentence {i}:")
                    print(f"    Text: {sentence['text'][:100]}...")
                    print(f"    Duration: {sentence['duration']/1000:.2f}s")
                    print(f"    Words: {sentence['word_count']}")
                    if sentence.get('speaker') is not None:
                        print(f"    Speaker: {sentence['speaker']}")
        except Exception as e:
            print(f"\nError during sentence generation: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Analysis mode (default)
        print("=" * 60)
        print("Word Gap Analysis for Sentence Segmentation")
        print("=" * 60)
        
        try:
            results = analyze_transcript(transcript_path, output_dir)
            print("\n" + "=" * 60)
            print("Analysis completed successfully!")
            print("=" * 60)
            print("\nTo generate sentences, run:")
            print(f"  python analyze_word_gaps.py {transcript_path} --generate-sentences")
        except Exception as e:
            print(f"\nError during analysis: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

