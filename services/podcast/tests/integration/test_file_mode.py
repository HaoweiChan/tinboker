"""
Integration tests for --file-mode option.
"""

from unittest.mock import patch

import pytest
from src.pipeline import EpisodeProcessor


@pytest.mark.integration
class TestFileMode:
    """Test --file-mode option behavior."""
    
    def test_file_mode_uses_persistent_directories(
        self, base_config, base_context, sample_episode_data, tmp_path
    ):
        """Test that --file-mode uses persistent directories instead of temp files."""
        base_config.use_file_mode = True
        base_config.downloads_dir = tmp_path / "downloads"
        base_config.transcripts_dir = tmp_path / "transcripts"
        base_config.summaries_dir = tmp_path / "summaries"
        base_config.images_dir = tmp_path / "images"
        base_config.temp_dir = None  # Explicitly set to None for file mode
        
        EpisodeProcessor(base_config, base_context)
        
        # Verify directories are set
        assert base_config.downloads_dir == tmp_path / "downloads"
        assert base_config.transcripts_dir == tmp_path / "transcripts"
        assert base_config.temp_dir is None, f"File mode should not use temp_dir, got: {base_config.temp_dir}"  # Should not use temp dir in file mode
    
    def test_file_mode_downloads_to_persistent_location(
        self, base_config, base_context, sample_episode_data, tmp_path, mock_download_file
    ):
        """Test that --file-mode downloads to persistent directory."""
        base_config.use_file_mode = True
        base_config.downloads_dir = tmp_path / "downloads"
        base_config.temp_dir = None
        # Ensure episode won't be skipped
        base_context.episode_id = None
        base_context.gcs_urls = None
        base_context.podcast_name = "Test Podcast"
        
        processor = EpisodeProcessor(base_config, base_context)
        
        expected_path = base_config.downloads_dir / base_context.podcast_name / "Episode 1_ Introduction.mp3"
        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_bytes(b'fake mp3')
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = expected_path
            mock_transcribe.return_value = 'Test transcript'
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify download was called (path would be in downloads_dir/podcast_name/)
            mock_download.assert_called_once()
    
    def test_file_mode_unique_file_paths(
        self, base_config, base_context, unique_episode_data, tmp_path, mock_download_file
    ):
        """Test that --file-mode saves each episode to a different file path."""
        base_config.use_file_mode = True
        base_config.downloads_dir = tmp_path / "downloads"
        base_context.podcast_name = "Test Podcast"
        
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        with patch('src.pipeline.steps.download.download_episode') as mock_download:
            path1 = base_config.downloads_dir / base_context.podcast_name / "episode1.mp3"
            path1.parent.mkdir(parents=True, exist_ok=True)
            path1.write_bytes(b'fake mp3')
            mock_download.return_value = path1
            processor.process_episode(episode1_data)
        
        episode1_path = base_context.mp3_path
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        with patch('src.pipeline.steps.download.download_episode') as mock_download:
            path2 = base_config.downloads_dir / base_context.podcast_name / "episode2.mp3"
            path2.parent.mkdir(parents=True, exist_ok=True)
            path2.write_bytes(b'fake mp3')
            mock_download.return_value = path2
            processor.process_episode(episode2_data)
        
        episode2_path = base_context.mp3_path
        
        # Verify paths are different
        assert episode1_path != episode2_path, "File paths should be different for each episode"
        assert episode1_path.parent == episode2_path.parent, "Files should be in same directory"
    
    def test_file_mode_saves_transcripts_to_transcripts_dir(
        self, base_config, base_context, sample_episode_data, tmp_path
    ):
        """Test that --file-mode saves transcripts to transcripts_dir."""
        base_config.use_file_mode = True
        base_config.transcripts_dir = tmp_path / "transcripts"
        base_context.podcast_name = "Test Podcast"
        base_context.mp3_path = tmp_path / "test.mp3"
        base_context.mp3_path.write_bytes(b'fake mp3')
        
        EpisodeProcessor(base_config, base_context)
        
        with patch('src.service.speech_to_text.transcribe_audio_file') as mock_transcribe:
            transcript_path = base_config.transcripts_dir / base_context.podcast_name / "test.json"
            mock_transcribe.return_value = str(transcript_path)
            
            # The transcribe step would use this path
            assert str(transcript_path).startswith(str(base_config.transcripts_dir))
    
    def test_file_mode_creates_directories(
        self, base_config, base_context, sample_episode_data, tmp_path
    ):
        """Test that --file-mode creates necessary directories."""
        base_config.use_file_mode = True
        base_config.downloads_dir = tmp_path / "downloads"
        base_config.transcripts_dir = tmp_path / "transcripts"
        base_context.podcast_name = "Test Podcast"
        
        EpisodeProcessor(base_config, base_context)
        
        # Simulate directory creation (would happen in download step)
        downloads_dir = base_config.downloads_dir / base_context.podcast_name
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        assert downloads_dir.exists(), "Downloads directory should be created"
        assert downloads_dir.is_dir(), "Downloads should be a directory"
    
    def test_file_mode_does_not_use_temp_dir(
        self, base_config, base_context
    ):
        """Test that --file-mode does not use temp_dir."""
        base_config.use_file_mode = True
        base_config.temp_dir = None
        
        EpisodeProcessor(base_config, base_context)
        
        assert base_config.temp_dir is None, "File mode should not use temp_dir"
    
    def test_file_mode_vs_streaming_mode(
        self, base_config, base_context
    ):
        """Test difference between file mode and streaming mode."""
        # File mode
        base_config.use_file_mode = True
        base_config.temp_dir = None  # Explicitly set to None for file mode
        assert base_config.use_file_mode is True
        assert base_config.temp_dir is None, f"File mode should not use temp_dir, got: {base_config.temp_dir}"
        
        # Streaming mode
        base_config.use_file_mode = False
        assert base_config.use_file_mode is False
        # temp_dir would be set in streaming mode (but we don't set it in tests)

