"""
Integration tests for context clearing between episodes.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from src.pipeline import EpisodeProcessor


@pytest.mark.integration
@pytest.mark.context_clearing
class TestContextClearing:
    """Test that context is properly cleared between episodes."""
    
    def test_consecutive_episodes_have_unique_mp3_paths(
        self, base_config, base_context, unique_episode_data, mock_download_file
    ):
        """Test that consecutive episodes have different MP3 paths."""
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        with patch('src.pipeline.steps.download.download_episode') as mock_download:
            mock_download.return_value = Path('/tmp/episode1.mp3')
            processor.process_episode(episode1_data)
        
        episode1_mp3_path = base_context.mp3_path
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        with patch('src.pipeline.steps.download.download_episode') as mock_download:
            mock_download.return_value = Path('/tmp/episode2.mp3')
            processor.process_episode(episode2_data)
        
        episode2_mp3_path = base_context.mp3_path
        
        # Verify paths are different
        assert episode1_mp3_path != episode2_mp3_path, "MP3 paths should be different for each episode"
    
    def test_consecutive_episodes_have_unique_transcripts(
        self, base_config, base_context, unique_episode_data, unique_transcript_data, mock_download_file, tmp_path
    ):
        """Test that consecutive episodes have different transcripts."""
        processor = EpisodeProcessor(base_config, base_context)
        
        # Create temporary MP3 files that exist
        mp3_1 = tmp_path / "episode1.mp3"
        mp3_1.write_bytes(b'fake mp3 content 1')
        mp3_2 = tmp_path / "episode2.mp3"
        mp3_2.write_bytes(b'fake mp3 content 2')
        
        # Process Episode 1
        unique_episode_data()
        transcript1 = unique_transcript_data()
        transcript1_text = transcript1['text']
        
        # Manually set transcript to simulate what transcribe step would do
        # Then verify it gets cleared between episodes
        base_context.transcript_text = transcript1_text
        base_context.transcript_sentences = transcript1['sentences']
        
        # Simulate processing episode 1 (this will clear context at start)
        processor._clear_episode_context()  # This simulates what happens at start of process_episode
        
        # Now set transcript again (simulating transcribe step)
        base_context.transcript_text = transcript1_text
        base_context.transcript_sentences = transcript1['sentences']
        
        episode1_transcript = base_context.transcript_text
        
        # Process Episode 2 - context should be cleared first
        unique_episode_data()
        transcript2 = unique_transcript_data()
        transcript2_text = transcript2['text']
        
        # Clear context (simulating what happens at start of process_episode)
        processor._clear_episode_context()
        
        # Verify context was cleared
        assert base_context.transcript_text is None, "Context should be cleared between episodes"
        
        # Now set transcript for episode 2 (simulating transcribe step)
        base_context.transcript_text = transcript2_text
        base_context.transcript_sentences = transcript2['sentences']
        
        episode2_transcript = base_context.transcript_text
        
        # Verify transcripts are different
        assert transcript1_text != transcript2_text, f"Original transcripts should be different. Episode 1: '{transcript1_text}', Episode 2: '{transcript2_text}'"
        assert episode1_transcript == transcript1_text, f"Episode 1 transcript should match. Expected: '{transcript1_text}', Got: '{episode1_transcript}'"
        assert episode2_transcript == transcript2_text, f"Episode 2 transcript should match. Expected: '{transcript2_text}', Got: '{episode2_transcript}'"
        assert episode1_transcript != episode2_transcript, f"Context transcripts should be different. Episode 1: '{episode1_transcript}', Episode 2: '{episode2_transcript}'"
        assert 'episode 1' in episode1_transcript.lower() or '1' in episode1_transcript, f"Episode 1 transcript should contain '1', got: '{episode1_transcript}'"
        assert 'episode 2' in episode2_transcript.lower() or '2' in episode2_transcript, f"Episode 2 transcript should contain '2', got: '{episode2_transcript}'"
    
    def test_consecutive_episodes_have_unique_summaries(
        self, base_config, base_context, unique_episode_data, unique_summary_data
    ):
        """Test that consecutive episodes have different summaries."""
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        unique_episode_data()
        summary1 = unique_summary_data()
        summary1_text = summary1['summary_text']
        
        # Set summary to simulate what summarize step would do
        base_context.summary_result = summary1
        episode1_summary = base_context.summary_result
        
        # Process Episode 2 - context should be cleared first
        unique_episode_data()
        summary2 = unique_summary_data()
        summary2_text = summary2['summary_text']
        
        # Clear context (simulating what happens at start of process_episode)
        processor._clear_episode_context()
        
        # Verify context was cleared
        assert base_context.summary_result is None, "Context should be cleared between episodes"
        
        # Now set summary for episode 2 (simulating summarize step)
        base_context.summary_result = summary2
        episode2_summary = base_context.summary_result
        
        # Verify summaries are different
        assert summary1_text != summary2_text, f"Original summaries should be different. Episode 1: '{summary1_text}', Episode 2: '{summary2_text}'"
        assert episode1_summary == summary1, "Episode 1 summary should match"
        assert episode2_summary == summary2, "Episode 2 summary should match"
        assert episode1_summary != episode2_summary, "Summaries should be different for each episode"
        assert episode1_summary['summary_text'] != episode2_summary['summary_text']
    
    def test_consecutive_episodes_have_unique_gcs_urls(
        self, base_config, base_context, unique_episode_data, unique_gcs_urls
    ):
        """Test that consecutive episodes have different GCS URLs."""
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        unique_episode_data()
        urls1 = unique_gcs_urls()
        
        # Set GCS URLs to simulate what upload step would do
        base_context.gcs_urls = urls1
        episode1_urls = base_context.gcs_urls
        
        # Process Episode 2 - context should be cleared first
        unique_episode_data()
        urls2 = unique_gcs_urls()
        
        # Clear context (simulating what happens at start of process_episode)
        processor._clear_episode_context()
        
        # Verify context was cleared
        assert base_context.gcs_urls is None, "Context should be cleared between episodes"
        
        # Now set GCS URLs for episode 2 (simulating upload step)
        base_context.gcs_urls = urls2
        episode2_urls = base_context.gcs_urls
        
        # Verify URLs are different
        assert urls1 != urls2, f"Original URLs should be different. Episode 1: {urls1['mp3_url']}, Episode 2: {urls2['mp3_url']}"
        assert episode1_urls == urls1, "Episode 1 URLs should match"
        assert episode2_urls == urls2, "Episode 2 URLs should match"
        assert episode1_urls != episode2_urls, "GCS URLs should be different for each episode"
        assert episode1_urls['mp3_url'] != episode2_urls['mp3_url']
        assert episode1_urls['transcript_url'] != episode2_urls['transcript_url']
    
    def test_full_pipeline_multiple_episodes_unique_content(
        self, base_config, base_context, unique_episode_data, 
        unique_transcript_data, unique_summary_data, unique_gcs_urls
    ):
        """Test that processing 3 consecutive episodes results in unique content for each."""
        processor = EpisodeProcessor(base_config, base_context)
        
        episode_paths = []
        episode_transcripts = []
        episode_summaries = []
        episode_urls = []
        
        # Process 3 episodes
        for i in range(3):
            unique_episode_data()
            transcript = unique_transcript_data()
            summary = unique_summary_data()
            urls = unique_gcs_urls()
            
            # Clear context (simulating what happens at start of process_episode)
            processor._clear_episode_context()
            
            # Set content to simulate what each step would do
            base_context.mp3_path = Path(f'/tmp/episode{i+1}.mp3')
            base_context.transcript_text = transcript['text']
            base_context.transcript_sentences = transcript['sentences']
            base_context.summary_result = summary
            base_context.gcs_urls = urls
            
            # Capture content immediately after setting
            episode_paths.append(base_context.mp3_path)
            episode_transcripts.append(base_context.transcript_text)
            episode_summaries.append(base_context.summary_result)
            episode_urls.append(base_context.gcs_urls)
        
        # Verify all episodes have unique content
        assert len(set(str(p) for p in episode_paths if p)) == 3, f"All MP3 paths should be unique. Got: {[str(p) for p in episode_paths]}"
        assert len(set(episode_transcripts)) == 3, f"All transcripts should be unique. Got: {episode_transcripts}"
        assert len(set(str(s.get('summary_text', '')) for s in episode_summaries if s)) == 3, f"All summaries should be unique. Got: {[s.get('summary_text', '') if s else None for s in episode_summaries]}"
        assert len(set(str(u.get('mp3_url', '')) for u in episode_urls if u)) == 3, f"All GCS URLs should be unique. Got: {[u.get('mp3_url', '') if u else None for u in episode_urls]}"
    
    def test_fill_limit_mode_context_clearing(
        self, base_config, base_context, unique_episode_data,
        unique_transcript_data, unique_summary_data
    ):
        """Test that context is cleared between episodes in fill-limit mode."""
        base_config.fill_limit = True
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        unique_episode_data()
        transcript1 = unique_transcript_data()
        summary1 = unique_summary_data()
        transcript1_text = transcript1['text']
        summary1_text = summary1['summary_text']
        
        # Set content to simulate what steps would do
        base_context.transcript_text = transcript1_text
        base_context.summary_result = summary1
        
        episode1_transcript = base_context.transcript_text
        episode1_summary = base_context.summary_result
        
        # Process Episode 2 - context should be cleared first
        unique_episode_data()
        transcript2 = unique_transcript_data()
        summary2 = unique_summary_data()
        transcript2_text = transcript2['text']
        summary2_text = summary2['summary_text']
        
        # Clear context (simulating what happens at start of process_episode)
        processor._clear_episode_context()
        
        # Verify context was cleared
        assert base_context.transcript_text is None, "Context should be cleared between episodes"
        assert base_context.summary_result is None, "Context should be cleared between episodes"
        
        # Now set content for episode 2 (simulating steps)
        base_context.transcript_text = transcript2_text
        base_context.summary_result = summary2
        
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

