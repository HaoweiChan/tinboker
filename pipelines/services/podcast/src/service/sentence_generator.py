#!/usr/bin/env python3
"""
Sentence Generation Service

This module provides a service for generating sentences from word-level transcripts
using duration-based segmentation (moving average + z-score analysis).

The algorithm detects words that are significantly longer than expected compared to
their neighbors, which likely contain pauses indicating sentence boundaries.
"""

from typing import Dict, List, Set

import numpy as np


class SentenceGenerator:
    """
    Service for generating sentences from word-level transcripts using duration-based segmentation.
    
    Uses moving average and z-score analysis to detect words with unusually long durations,
    which typically indicate sentence boundaries when pauses are "absorbed" into word timestamps.
    """
    
    def __init__(
        self,
        window_size: int = 8,
        z_threshold: float = 2.0,
        require_longer_than_neighbors: bool = True,
        neighbor_ratio_threshold: float = 1.5,
        min_sentence_length: int = 3,
        min_words_before: int = 3
    ):
        """
        Initialize the Sentence Generator service.
        
        Args:
            window_size: Size of moving window for calculating statistics (default: 8)
            z_threshold: Z-score threshold for detecting anomalies (default: 2.0)
            require_longer_than_neighbors: If True, word must be longer than both previous 
                                          and next words (default: True)
            neighbor_ratio_threshold: Ratio threshold for neighbor comparison (default: 1.5x)
            min_sentence_length: Minimum number of words per sentence (default: 3)
            min_words_before: Minimum words before first boundary can be detected (default: 3)
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.require_longer_than_neighbors = require_longer_than_neighbors
        self.neighbor_ratio_threshold = neighbor_ratio_threshold
        self.min_sentence_length = min_sentence_length
        self.min_words_before = min_words_before
    
    def generate_sentences(self, words: List[Dict]) -> List[Dict]:
        """
        Generate sentences from word-level transcript using duration-based segmentation.
        
        Args:
            words: List of word dictionaries, each containing:
                  - 'text': str - Word text
                  - 'start': float - Start time in milliseconds
                  - 'end': float - End time in milliseconds
                  - 'confidence': Optional[float] - Confidence score (0.0-1.0)
                  - 'speaker': Optional[str] - Speaker ID
        
        Returns:
            List of sentence dictionaries, each containing:
            - 'text': str - Full sentence text
            - 'words': List[Dict] - Word dictionaries in this sentence
            - 'start': float - Start time of first word (ms)
            - 'end': float - End time of last word (ms)
            - 'duration': float - Total duration (ms)
            - 'confidence': float - Average confidence of words
            - 'speaker': Optional[str] - Speaker ID if available
            - 'word_count': int - Number of words in sentence
        
        Raises:
            ValueError: If words list is empty or invalid
        """
        if not words:
            return []
        
        # Validate word structure
        self._validate_words(words)
        
        # Detect sentence boundaries
        boundary_indices = self._detect_boundaries(words)
        
        # Build sentences from boundaries
        sentences = self._build_sentences(words, boundary_indices)
        
        return sentences
    
    def _validate_words(self, words: List[Dict]) -> None:
        """
        Validate that words have required fields.
        
        Args:
            words: List of word dictionaries
            
        Raises:
            ValueError: If words are invalid
        """
        if not isinstance(words, list):
            raise ValueError("Words must be a list")
        
        for i, word in enumerate(words):
            if not isinstance(word, dict):
                raise ValueError(f"Word at index {i} must be a dictionary")
            
            required_fields = ['text', 'start', 'end']
            for field in required_fields:
                if field not in word:
                    raise ValueError(f"Word at index {i} missing required field: {field}")
            
            # Validate time values
            if not isinstance(word['start'], (int, float)) or not isinstance(word['end'], (int, float)):
                raise ValueError(f"Word at index {i} has invalid start/end time values")
            
            if word['end'] < word['start']:
                raise ValueError(f"Word at index {i} has end time before start time")
    
    def _calculate_word_durations(self, words: List[Dict]) -> List[float]:
        """
        Calculate duration of each word.
        
        Args:
            words: List of word dictionaries
            
        Returns:
            List of durations in milliseconds
        """
        return [word['end'] - word['start'] for word in words]
    
    def _calculate_moving_stats(self, durations: List[float]) -> List[Dict]:
        """
        Calculate moving average and standard deviation for each word position.
        
        For each word i, calculates stats from words [i-window_size : i-1].
        
        Args:
            durations: List of word durations in milliseconds
            
        Returns:
            List of dictionaries containing:
            - 'word_idx': int - Index of the word
            - 'duration': float - Word duration
            - 'moving_avg': float - Moving average of previous window_size words
            - 'moving_std': float - Moving standard deviation
            - 'z_score': float - Z-score of current word duration
        """
        moving_stats = []
        
        for i in range(len(durations)):
            duration = durations[i]
            
            # Get window of previous words
            window_start = max(0, i - self.window_size)
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
            
            moving_stats.append({
                'word_idx': i,
                'duration': duration,
                'moving_avg': moving_avg,
                'moving_std': moving_std,
                'z_score': z_score
            })
        
        return moving_stats
    
    def _detect_boundaries(self, words: List[Dict]) -> Set[int]:
        """
        Detect sentence boundary indices based on duration anomalies.
        
        Args:
            words: List of word dictionaries
            
        Returns:
            Set of word indices that mark sentence boundaries
        """
        durations = self._calculate_word_durations(words)
        moving_stats = self._calculate_moving_stats(durations)
        boundaries = set()
        
        for i, stats in enumerate(moving_stats):
            z_score = stats['z_score']
            current_duration = stats['duration']
            
            # Check if this is an anomaly based on z-score
            is_z_anomaly = (
                z_score >= self.z_threshold and
                i >= self.min_words_before and
                not np.isinf(z_score) and
                not np.isnan(z_score)
            )
            
            if not is_z_anomaly:
                continue
            
            # Additional check: must be longer than both previous and next words
            if self.require_longer_than_neighbors:
                # Get previous word duration
                prev_duration = durations[i - 1] if i > 0 else None
                # Get next word duration
                next_duration = durations[i + 1] if i < len(words) - 1 else None
                
                # Check if current word is significantly longer than both neighbors
                longer_than_prev = True
                longer_than_next = True
                
                if prev_duration is not None:
                    longer_than_prev = current_duration >= prev_duration * self.neighbor_ratio_threshold
                
                if next_duration is not None:
                    longer_than_next = current_duration >= next_duration * self.neighbor_ratio_threshold
                
                # Must be longer than both neighbors (or at least one if at boundary)
                if not (longer_than_prev and longer_than_next):
                    # If we're at the start or end, be more lenient
                    if i == 0 and longer_than_next:
                        pass  # OK at start
                    elif i == len(words) - 1 and longer_than_prev:
                        pass  # OK at end
                    else:
                        continue  # Skip this word - not longer than both neighbors
            
            # This is a boundary
            boundaries.add(i)
        
        return boundaries
    
    def _build_sentences(self, words: List[Dict], boundary_indices: Set[int]) -> List[Dict]:
        """
        Build sentences from words using detected boundaries.
        
        Args:
            words: List of word dictionaries
            boundary_indices: Set of word indices that mark sentence boundaries
            
        Returns:
            List of sentence dictionaries
        """
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
            if (is_boundary and len(current_sentence_words) >= self.min_sentence_length) or is_last_word:
                if current_sentence_words:
                    sentence = self._create_sentence(current_sentence_words)
                    sentences.append(sentence)
                    current_sentence_words = []
        
        # Handle any remaining words
        if current_sentence_words:
            if len(sentences) > 0:
                # Merge with last sentence if too short
                if len(current_sentence_words) < self.min_sentence_length:
                    sentences[-1]['words'].extend(current_sentence_words)
                    sentences[-1] = self._create_sentence(sentences[-1]['words'])
                else:
                    sentence = self._create_sentence(current_sentence_words)
                    sentences.append(sentence)
            else:
                sentence = self._create_sentence(current_sentence_words)
                sentences.append(sentence)
        
        return sentences
    
    def _create_sentence(self, words: List[Dict]) -> Dict:
        """
        Create a sentence dictionary from a list of words.
        
        Args:
            words: List of word dictionaries
            
        Returns:
            Sentence dictionary with text, timing, confidence, and metadata
        """
        if not words:
            raise ValueError("Cannot create sentence from empty word list")
        
        # Extract text
        text = "".join([w['text'] for w in words])
        
        # Calculate timing
        start = words[0]['start']
        end = words[-1]['end']
        duration = end - start
        
        # Calculate average confidence
        confidences = [
            w.get('confidence', 0.0) for w in words
            if w.get('confidence') is not None
        ]
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




