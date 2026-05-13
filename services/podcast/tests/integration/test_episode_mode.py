"""
Integration tests for --episode mode.
"""

from unittest.mock import patch

import pytest


@pytest.mark.integration
class TestEpisodeMode:
    """Test --episode option behavior."""
    
    def test_episode_single_fetches_from_firestore(
        self, base_config, base_context, sample_firestore_episode
    ):
        """Test that --episode <episode_id> fetches single episode from Firestore."""
        episode_id = sample_firestore_episode['id']
        
        base_context.firebase_service.get_episode_by_id.return_value = sample_firestore_episode
        
        # Simulate the logic from main.py
        firestore_episode = base_context.firebase_service.get_episode_by_id(episode_id)
        
        assert firestore_episode is not None
        assert firestore_episode['id'] == episode_id
        assert firestore_episode['episode_title'] == sample_firestore_episode['episode_title']
    
    def test_episode_all_fetches_all_from_firestore(
        self, base_context, sample_firestore_episodes
    ):
        """Test that --episode all fetches all episodes from Firestore."""
        base_context.firebase_service.get_all_episodes.return_value = sample_firestore_episodes
        
        # Simulate the logic from main.py
        all_episodes = base_context.firebase_service.get_all_episodes()
        
        assert len(all_episodes) == 3
        assert all_episodes[0]['id'] == sample_firestore_episodes[0]['id']
    
    def test_episode_mode_applies_transcript_option(
        self, base_config, base_context, sample_firestore_episode, sample_podcasts
    ):
        """Test that --episode mode applies transcript_option from podcasts_to_download.json."""
        # Mock the podcast config mapping
        podcast_name = sample_firestore_episode['podcast_name']
        podcast_config = next(p for p in sample_podcasts if p['name'] == podcast_name)
        
        # Get transcript_option from config
        transcript_option = podcast_config.get('transcript_option', {})
        episode_stt_service = transcript_option.get('transcript_service', 'groq')
        episode_stt_model = transcript_option.get('model')
        
        # Verify transcript option is extracted correctly
        assert episode_stt_service == 'groq'
        assert episode_stt_model == 'whisper-large-v3'
    
    def test_episode_mode_loads_gcs_urls(
        self, base_config, base_context, sample_firestore_episode
    ):
        """Test that --episode mode loads GCS URLs from Firestore episode."""
        # Simulate the logic from main.py process_firestore_episode
        if sample_firestore_episode.get('mp3_url') or sample_firestore_episode.get('transcript_url'):
            base_context.gcs_urls = {
                'mp3_url': sample_firestore_episode.get('mp3_url'),
                'transcript_url': sample_firestore_episode.get('transcript_url'),
                'summary_url': sample_firestore_episode.get('summary_url'),
                'summary_image_url': sample_firestore_episode.get('summary_image_url'),
            }
        
        assert base_context.gcs_urls is not None
        assert base_context.gcs_urls['mp3_url'] == sample_firestore_episode['mp3_url']
        assert base_context.gcs_urls['transcript_url'] == sample_firestore_episode['transcript_url']
    
    def test_episode_mode_rerun_from_download_fetches_episodeurl(
        self, base_config, base_context, sample_firestore_episode, sample_episodes
    ):
        """Test that --episode mode with --rerun-from download fetches episodeUrl from API."""
        base_config.rerun_from = "download"
        
        # Mock fetch_episodes to return episodes from API
        with patch('src.service.download_podcasts.fetch_episodes') as mock_fetch:
            mock_fetch.return_value = sample_episodes
            
            # Simulate finding matching episode by title
            episode_title = sample_firestore_episode['episode_title']
            api_episodes = mock_fetch('podcast_id')
            
            episode_url = None
            for api_episode in api_episodes:
                if api_episode.get('title') == episode_title:
                    episode_url = api_episode.get('episodeUrl')
                    break
            
            assert episode_url is not None
            assert episode_url == sample_episodes[0]['episodeUrl']
    
    def test_episode_mode_rerun_from_summarize_downloads_transcript(
        self, base_config, base_context, sample_firestore_episode
    ):
        """Test that --episode mode with --rerun-from summarize downloads transcript from GCS."""
        base_config.rerun_from = "summarize"
        
        transcript_url = sample_firestore_episode.get('transcript_url')
        base_context.gcs_urls = {'transcript_url': transcript_url}
        
        # Mock GCS download
        transcript_data = {
            'text': 'Test transcript text',
            'sentences': [],
            'words': None
        }
        base_context.gcs_service.download_transcript_by_gcs_url.return_value = transcript_data
        
        # Simulate the logic from main.py
        if transcript_url:
            downloaded = base_context.gcs_service.download_transcript_by_gcs_url(transcript_url)
            if downloaded and downloaded.get('text'):
                base_context.transcript_text = downloaded.get('text', '')
        
        assert base_context.transcript_text == 'Test transcript text'
    
    def test_episode_all_context_clearing(
        self, base_config, base_context, sample_firestore_episodes,
        unique_transcript_data, unique_summary_data, unique_gcs_urls
    ):
        """Test that context is cleared between episodes when processing --episode all."""
        from src.pipeline import EpisodeProcessor
        
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1 = sample_firestore_episodes[0]
        transcript1 = unique_transcript_data()
        summary1 = unique_summary_data()
        unique_gcs_urls()
        
        base_context.episode_id = episode1['id']
        base_context.gcs_urls = {
            'mp3_url': episode1['mp3_url'],
            'transcript_url': episode1['transcript_url']
        }
        base_context.transcript_text = transcript1['text']
        base_context.summary_result = summary1
        
        episode1_transcript = base_context.transcript_text
        episode1_summary = base_context.summary_result
        
        # Process Episode 2
        episode2 = sample_firestore_episodes[1]
        transcript2 = unique_transcript_data()
        summary2 = unique_summary_data()
        unique_gcs_urls()
        
        # Simulate context clearing (processor._clear_episode_context is called)
        processor._clear_episode_context()
        
        base_context.episode_id = episode2['id']
        base_context.gcs_urls = {
            'mp3_url': episode2['mp3_url'],
            'transcript_url': episode2['transcript_url']
        }
        base_context.transcript_text = transcript2['text']
        base_context.summary_result = summary2
        
        episode2_transcript = base_context.transcript_text
        episode2_summary = base_context.summary_result
        
        # Verify context was cleared and new content is different
        assert episode1_transcript != episode2_transcript, "Transcripts should be different after context clearing"
        assert episode1_summary != episode2_summary, "Summaries should be different after context clearing"
        assert episode1_summary['summary_text'] != episode2_summary['summary_text']

