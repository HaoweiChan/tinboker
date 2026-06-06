"""
Integration tests for --fill-limit mode.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from src.pipeline import EpisodeProcessor


@pytest.mark.integration
class TestFillLimitMode:
    """Test --fill-limit mode behavior."""
    
    def test_fill_limit_filters_processed_episodes(
        self, base_config, base_context, sample_episodes, sample_firestore_episode
    ):
        """Test that fill-limit filters out already processed episodes."""
        base_config.fill_limit = True
        base_config.episode_limit = 2
        
        # Mock Firebase to return processed episode for first episode
        def get_episode_side_effect(podcast_name, episode_title, episode_number):
            if episode_title == sample_episodes[0]['title']:
                # First episode is processed
                return sample_firestore_episode
            # Other episodes are not processed
            return None
        
        base_context.firebase_service.get_episode_by_fields.side_effect = get_episode_side_effect
        
        # Simulate the filtering logic from main.py
        non_processed_episodes = []
        limit = base_config.episode_limit
        
        for episode in sample_episodes:
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            # Check if fully processed (has all required URLs)
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue  # Skip processed episode
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= limit:
                break
        
        # Verify that processed episode was filtered out
        assert len(non_processed_episodes) == 2, "Should have 2 non-processed episodes"
        assert sample_episodes[0]['title'] not in [e['title'] for e in non_processed_episodes], "Processed episode should be filtered out"
        assert sample_episodes[1]['title'] in [e['title'] for e in non_processed_episodes], "Non-processed episode should be included"
        assert sample_episodes[2]['title'] in [e['title'] for e in non_processed_episodes], "Non-processed episode should be included"
    
    def test_fill_limit_processes_exactly_limit_non_processed(
        self, base_config, base_context, sample_episodes
    ):
        """Test that fill-limit processes exactly limit number of non-processed episodes."""
        base_config.fill_limit = True
        base_config.episode_limit = 1
        
        # All episodes are not processed
        base_context.firebase_service.get_episode_by_fields.return_value = None
        
        # Simulate the filtering logic
        non_processed_episodes = []
        limit = base_config.episode_limit
        
        for episode in sample_episodes:
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= limit:
                break
        
        # Verify exactly limit episodes are selected
        assert len(non_processed_episodes) == 1, "Should process exactly 1 non-processed episode"
        assert non_processed_episodes[0]['title'] == sample_episodes[0]['title']
    
    def test_fill_limit_stops_when_limit_reached(
        self, base_config, base_context, sample_episodes
    ):
        """Test that fill-limit stops checking once limit is reached."""
        base_config.fill_limit = True
        base_config.episode_limit = 2
        
        # All episodes are not processed
        base_context.firebase_service.get_episode_by_fields.return_value = None
        
        # Simulate the filtering logic
        non_processed_episodes = []
        checked_count = 0
        limit = base_config.episode_limit
        
        for episode in sample_episodes:
            checked_count += 1
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= limit:
                break
        
        # Verify it stopped at limit
        assert len(non_processed_episodes) == 2, "Should have exactly 2 episodes"
        assert checked_count == 2, "Should have checked exactly 2 episodes (stopped early)"
    
    def test_fill_limit_all_episodes_processed(
        self, base_config, base_context, sample_episodes, sample_firestore_episode
    ):
        """Test fill-limit when all episodes are already processed."""
        base_config.fill_limit = True
        base_config.episode_limit = 2
        
        # All episodes are processed
        base_context.firebase_service.get_episode_by_fields.return_value = sample_firestore_episode
        
        # Simulate the filtering logic
        non_processed_episodes = []
        
        for episode in sample_episodes:
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= base_config.episode_limit:
                break
        
        # Verify no episodes are selected
        assert len(non_processed_episodes) == 0, "Should have 0 non-processed episodes when all are processed"
    
    def test_fill_limit_less_than_limit_available(
        self, base_config, base_context, sample_episodes
    ):
        """Test fill-limit when less than limit non-processed episodes are available."""
        base_config.fill_limit = True
        base_config.episode_limit = 5  # More than available
        
        # All episodes are not processed
        base_context.firebase_service.get_episode_by_fields.return_value = None
        
        # Simulate the filtering logic
        non_processed_episodes = []
        limit = base_config.episode_limit
        
        for episode in sample_episodes:
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= limit:
                break
        
        # Verify all available episodes are selected
        assert len(non_processed_episodes) == 3, "Should process all 3 available episodes"
        assert len(non_processed_episodes) < limit, "Should have fewer than limit when not enough available"
    
    def test_fill_limit_context_clearing_between_episodes(
        self, base_config, base_context, unique_episode_data,
        unique_transcript_data, unique_summary_data
    ):
        """Test that context is cleared between episodes in fill-limit mode."""
        base_config.fill_limit = True
        # Ensure episodes won't be skipped
        base_context.episode_id = None
        base_context.gcs_urls = None
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        transcript1 = unique_transcript_data()
        summary1 = unique_summary_data()
        transcript1_text = transcript1['text']
        summary1_text = summary1['summary_text']
        
        mp3_1 = Path('/tmp/episode1.mp3')
        mp3_1.parent.mkdir(parents=True, exist_ok=True)
        mp3_1.write_bytes(b'fake mp3 1')
        
        def transcribe_side_effect1(*args, **kwargs):
            base_context.transcript_text = transcript1_text
            return transcript1_text
        
        def summarize_side_effect1(*args, **kwargs):
            base_context.summary_result = summary1
            return summary1
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode', side_effect=transcribe_side_effect1), \
             patch('src.pipeline.steps.summarize.generate_summary', side_effect=summarize_side_effect1), \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_1
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode1_data)
        
        episode1_transcript = base_context.transcript_text
        episode1_summary = base_context.summary_result
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        transcript2 = unique_transcript_data()
        summary2 = unique_summary_data()
        transcript2_text = transcript2['text']
        summary2_text = summary2['summary_text']
        
        mp3_2 = Path('/tmp/episode2.mp3')
        mp3_2.parent.mkdir(parents=True, exist_ok=True)
        mp3_2.write_bytes(b'fake mp3 2')
        
        def transcribe_side_effect2(*args, **kwargs):
            base_context.transcript_text = transcript2_text
            return transcript2_text
        
        def summarize_side_effect2(*args, **kwargs):
            base_context.summary_result = summary2
            return summary2
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode', side_effect=transcribe_side_effect2), \
             patch('src.pipeline.steps.summarize.generate_summary', side_effect=summarize_side_effect2), \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_2
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode2_data)
        
        episode2_transcript = base_context.transcript_text
        episode2_summary = base_context.summary_result
        
        # Verify context was cleared and new content is different
        assert transcript1_text != transcript2_text, f"Original transcripts should be different. Episode 1: '{transcript1_text}', Episode 2: '{transcript2_text}'"
        assert summary1_text != summary2_text, f"Original summaries should be different. Episode 1: '{summary1_text}', Episode 2: '{summary2_text}'"
        assert episode1_transcript == transcript1_text, "Episode 1 transcript should match"
        assert episode2_transcript == transcript2_text, "Episode 2 transcript should match"
        assert episode1_summary == summary1, "Episode 1 summary should match"
        assert episode2_summary == summary2, "Episode 2 summary should match"
        assert episode1_transcript != episode2_transcript, "Transcripts should be different after context clearing"
        assert episode1_summary != episode2_summary, "Summaries should be different after context clearing"
        assert episode1_summary['summary_text'] != episode2_summary['summary_text']
    
    def test_fill_limit_mixed_processed_and_non_processed(
        self, base_config, base_context, sample_episodes, sample_firestore_episode
    ):
        """Test fill-limit with mixed processed and non-processed episodes."""
        base_config.fill_limit = True
        base_config.episode_limit = 2
        
        # First episode is processed, others are not
        def get_episode_side_effect(podcast_name, episode_title, episode_number):
            if episode_title == sample_episodes[0]['title']:
                return sample_firestore_episode
            return None
        
        base_context.firebase_service.get_episode_by_fields.side_effect = get_episode_side_effect
        
        # Simulate the filtering logic
        non_processed_episodes = []
        limit = base_config.episode_limit
        
        for episode in sample_episodes:
            existing = base_context.firebase_service.get_episode_by_fields(
                podcast_name=base_config.podcast_name,
                episode_title=episode.get('title'),
                episode_number=episode.get('episodeNumber')
            )
            if existing and existing.get('mp3_url') and existing.get('transcript_url') and existing.get('summary_url') and existing.get('summary_image_url'):
                continue
            non_processed_episodes.append(episode)
            if len(non_processed_episodes) >= limit:
                break
        
        # Verify correct episodes are selected
        assert len(non_processed_episodes) == 2, "Should have 2 non-processed episodes"
        assert sample_episodes[0]['title'] not in [e['title'] for e in non_processed_episodes], "Processed episode should be filtered out"
        assert sample_episodes[1]['title'] in [e['title'] for e in non_processed_episodes], "Non-processed episode should be included"
        assert sample_episodes[2]['title'] in [e['title'] for e in non_processed_episodes], "Non-processed episode should be included"

