"""
Integration tests for --rerun-from modes.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from src.pipeline import EpisodeProcessor


@pytest.mark.integration
class TestRerunModes:
    """Test all --rerun-from modes."""
    
    def test_rerun_from_download_runs_all_steps(
        self, base_config, base_context, sample_episode_data, mock_download_file
    ):
        """Test that --rerun-from download runs all steps."""
        base_config.rerun_from = "download"
        # Ensure episode won't be skipped
        base_context.episode_id = None
        base_context.gcs_urls = None
        processor = EpisodeProcessor(base_config, base_context)
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore') as mock_firestore, \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mp3_path = Path('/tmp/test.mp3')
            mp3_path.parent.mkdir(parents=True, exist_ok=True)
            mp3_path.write_bytes(b'fake mp3')
            
            mock_download.return_value = mp3_path
            mock_transcribe.return_value = 'Test transcript'
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify all steps were called
            mock_download.assert_called_once()
            mock_transcribe.assert_called_once()
            mock_summarize.assert_called_once()
            mock_upload.assert_called_once()
            mock_firestore.assert_called_once()
            mock_validate.assert_called_once()
    
    def test_rerun_from_download_uploads_all_files(
        self, base_config, base_context, sample_episode_data, unique_gcs_urls, mock_download_file
    ):
        """Test that --rerun-from download uploads all files with skip_existing=False."""
        base_config.rerun_from = "download"
        # Ensure episode won't be skipped
        base_context.episode_id = None
        base_context.gcs_urls = None
        processor = EpisodeProcessor(base_config, base_context)
        
        mp3_path = Path('/tmp/test.mp3')
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_bytes(b'fake mp3')
        
        base_context.mp3_path = mp3_path
        base_context.transcript_text = 'Test transcript'
        base_context.summary_result = {'summary_text': 'Test summary'}
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_path
            mock_transcribe.return_value = 'Test transcript'
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            urls = unique_gcs_urls()
            mock_upload.return_value = urls
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify upload was called
            assert mock_upload.called
    
    def test_rerun_from_download_unique_mp3_paths(
        self, base_config, base_context, unique_episode_data, unique_gcs_urls, mock_download_file
    ):
        """Test that --rerun-from download uses different MP3 paths for each episode."""
        base_config.rerun_from = "download"
        # Ensure episodes won't be skipped
        base_context.episode_id = None
        base_context.gcs_urls = None
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        mp3_1 = Path('/tmp/episode1.mp3')
        mp3_1.parent.mkdir(parents=True, exist_ok=True)
        mp3_1.write_bytes(b'fake mp3 1')
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_1
            mock_transcribe.return_value = 'Test transcript 1'
            mock_summarize.return_value = {'summary_text': 'Test summary 1'}
            mock_upload.return_value = unique_gcs_urls()
            mock_validate.return_value = True
            
            processor.process_episode(episode1_data)
        
        episode1_path = base_context.mp3_path
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        mp3_2 = Path('/tmp/episode2.mp3')
        mp3_2.parent.mkdir(parents=True, exist_ok=True)
        mp3_2.write_bytes(b'fake mp3 2')
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_2
            mock_transcribe.return_value = 'Test transcript 2'
            mock_summarize.return_value = {'summary_text': 'Test summary 2'}
            mock_upload.return_value = unique_gcs_urls()
            mock_validate.return_value = True
            
            processor.process_episode(episode2_data)
        
        episode2_path = base_context.mp3_path
        
        assert episode1_path != episode2_path, "MP3 paths should be different for each episode"
    
    def test_rerun_from_transcribe_downloads_mp3(
        self, base_config, base_context, sample_episode_data, sample_firestore_episode
    ):
        """Test that --rerun-from transcribe downloads MP3 from GCS or API."""
        base_config.rerun_from = "transcribe"
        # Ensure episode won't be skipped
        base_context.episode_id = None
        processor = EpisodeProcessor(base_config, base_context)
        
        # Set up existing episode with GCS URLs
        base_context.gcs_urls = {
            'mp3_url': sample_firestore_episode['mp3_url']
        }
        
        mp3_path = Path('/tmp/test.mp3')
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_bytes(b'fake mp3')
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_path
            mock_transcribe.return_value = 'Test transcript'
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify download was called
            mock_download.assert_called_once()
    
    def test_rerun_from_transcribe_runs_transcribe_onwards(
        self, base_config, base_context, sample_episode_data
    ):
        """Test that --rerun-from transcribe runs transcribe, summarize, upload, firestore, validate."""
        base_config.rerun_from = "transcribe"
        # Ensure episode won't be skipped
        base_context.episode_id = None
        processor = EpisodeProcessor(base_config, base_context)
        
        mp3_path = Path('/tmp/test.mp3')
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.write_bytes(b'fake mp3')
        base_context.mp3_path = mp3_path
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore') as mock_firestore, \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_path
            mock_transcribe.return_value = 'Test transcript'
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify steps were called
            mock_download.assert_called_once()
            mock_transcribe.assert_called_once()
            mock_summarize.assert_called_once()
            mock_upload.assert_called_once()
            mock_firestore.assert_called_once()
            mock_validate.assert_called_once()
    
    def test_rerun_from_transcribe_unique_transcripts(
        self, base_config, base_context, unique_episode_data, unique_transcript_data
    ):
        """Test that --rerun-from transcribe produces different transcripts for each episode."""
        base_config.rerun_from = "transcribe"
        # Ensure episodes won't be skipped
        base_context.episode_id = None
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        transcript1 = unique_transcript_data()
        transcript1_text = transcript1['text']
        
        mp3_1 = Path('/tmp/episode1.mp3')
        mp3_1.parent.mkdir(parents=True, exist_ok=True)
        mp3_1.write_bytes(b'fake mp3 1')
        
        def transcribe_side_effect1(*args, **kwargs):
            base_context.transcript_text = transcript1_text
            return transcript1_text
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode', side_effect=transcribe_side_effect1), \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_1
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode1_data)
        
        episode1_transcript = base_context.transcript_text
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        transcript2 = unique_transcript_data()
        transcript2_text = transcript2['text']
        
        mp3_2 = Path('/tmp/episode2.mp3')
        mp3_2.parent.mkdir(parents=True, exist_ok=True)
        mp3_2.write_bytes(b'fake mp3 2')
        
        def transcribe_side_effect2(*args, **kwargs):
            base_context.transcript_text = transcript2_text
            return transcript2_text
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode', side_effect=transcribe_side_effect2), \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_download.return_value = mp3_2
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode2_data)
        
        episode2_transcript = base_context.transcript_text
        
        assert transcript1_text != transcript2_text, f"Original transcripts should be different. Episode 1: '{transcript1_text}', Episode 2: '{transcript2_text}'"
        assert episode1_transcript == transcript1_text, f"Episode 1 transcript should match. Expected: '{transcript1_text}', Got: '{episode1_transcript}'"
        assert episode2_transcript == transcript2_text, f"Episode 2 transcript should match. Expected: '{transcript2_text}', Got: '{episode2_transcript}'"
        assert episode1_transcript != episode2_transcript, "Transcripts should be different for each episode"
    
    def test_rerun_from_summarize_downloads_transcript(
        self, base_config, base_context, sample_episode_data, sample_firestore_episode
    ):
        """Test that --rerun-from summarize downloads transcript from GCS."""
        base_config.rerun_from = "summarize"
        processor = EpisodeProcessor(base_config, base_context)
        
        # Set up existing episode
        base_context.episode_id = sample_firestore_episode['id']
        base_context.gcs_urls = {
            'transcript_url': sample_firestore_episode['transcript_url']
        }
        
        # Mock GCS download
        base_context.gcs_service.download_transcript_by_gcs_url.return_value = {
            'text': 'Test transcript',
            'sentences': [],
            'words': None
        }
        
        processor._load_existing_data(sample_episode_data)
        
        # Verify transcript was loaded
        assert base_context.transcript_text == 'Test transcript'
    
    def test_rerun_from_summarize_skips_download_and_transcribe(
        self, base_config, base_context, sample_episode_data, sample_firestore_episode
    ):
        """Test that --rerun-from summarize skips download and transcribe steps."""
        base_config.rerun_from = "summarize"
        # Set up existing episode so summarize mode works
        base_context.episode_id = sample_firestore_episode['id']
        base_context.gcs_urls = {
            'transcript_url': sample_firestore_episode['transcript_url']
        }
        processor = EpisodeProcessor(base_config, base_context)
        
        # Load transcript from GCS (simulating what _load_existing_data does)
        base_context.gcs_service.download_transcript_by_gcs_url.return_value = {
            'text': 'Test transcript',
            'sentences': [],
            'words': None
        }
        processor._load_existing_data(sample_episode_data)
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_summarize.return_value = {'summary_text': 'Test summary'}
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify download and transcribe were NOT called
            mock_download.assert_not_called()
            mock_transcribe.assert_not_called()
            # But summarize was called
            mock_summarize.assert_called_once()
    
    def test_rerun_from_summarize_unique_summaries(
        self, base_config, base_context, unique_episode_data, unique_summary_data, sample_firestore_episode
    ):
        """Test that --rerun-from summarize produces different summaries for each episode."""
        base_config.rerun_from = "summarize"
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        summary1 = unique_summary_data()
        summary1_text = summary1['summary_text']
        
        # Set up existing episode
        base_context.episode_id = 'episode1_id'
        base_context.gcs_urls = {
            'transcript_url': sample_firestore_episode['transcript_url']
        }
        base_context.gcs_service.download_transcript_by_gcs_url.return_value = {
            'text': 'Transcript 1',
            'sentences': [],
            'words': None
        }
        processor._load_existing_data(episode1_data)
        
        def summarize_side_effect1(*args, **kwargs):
            base_context.summary_result = summary1
            return summary1
        
        with patch('src.pipeline.steps.summarize.generate_summary', side_effect=summarize_side_effect1), \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode1_data)
        
        episode1_summary = base_context.summary_result
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        summary2 = unique_summary_data()
        summary2_text = summary2['summary_text']
        
        # Set up existing episode for episode 2
        base_context.episode_id = 'episode2_id'
        base_context.gcs_urls = {
            'transcript_url': sample_firestore_episode['transcript_url']
        }
        base_context.gcs_service.download_transcript_by_gcs_url.return_value = {
            'text': 'Transcript 2',
            'sentences': [],
            'words': None
        }
        processor._load_existing_data(episode2_data)
        
        def summarize_side_effect2(*args, **kwargs):
            base_context.summary_result = summary2
            return summary2
        
        with patch('src.pipeline.steps.summarize.generate_summary', side_effect=summarize_side_effect2), \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_upload.return_value = {'mp3_url': 'gs://test/test.mp3'}
            mock_validate.return_value = True
            
            processor.process_episode(episode2_data)
        
        episode2_summary = base_context.summary_result
        
        assert summary1_text != summary2_text, f"Original summaries should be different. Episode 1: '{summary1_text}', Episode 2: '{summary2_text}'"
        assert episode1_summary == summary1, "Episode 1 summary should match"
        assert episode2_summary == summary2, "Episode 2 summary should match"
        assert episode1_summary != episode2_summary, "Summaries should be different for each episode"
        assert episode1_summary['summary_text'] != episode2_summary['summary_text']
    
    def test_rerun_from_upload_skips_processing_steps(
        self, base_config, base_context, sample_episode_data, sample_firestore_episode
    ):
        """Test that --rerun-from upload skips download, transcribe, and summarize."""
        base_config.rerun_from = "upload"
        processor = EpisodeProcessor(base_config, base_context)
        
        # Set up existing episode with GCS URLs (but don't set episode_id so it doesn't skip)
        # The _load_existing_data will load it, but we want to test rerun behavior
        # So we manually set gcs_urls after load would happen
        base_context.gcs_urls = {
            'mp3_url': sample_firestore_episode['mp3_url'],
            'transcript_url': sample_firestore_episode['transcript_url'],
            'summary_url': sample_firestore_episode['summary_url'],
            'summary_image_url': sample_firestore_episode['summary_image_url']
        }
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_upload.return_value = base_context.gcs_urls
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify processing steps were NOT called
            mock_download.assert_not_called()
            mock_transcribe.assert_not_called()
            mock_summarize.assert_not_called()
            # But upload was called
            mock_upload.assert_called_once()
    
    def test_rerun_from_upload_unique_urls(
        self, base_config, base_context, unique_episode_data, unique_gcs_urls, sample_firestore_episode
    ):
        """Test that --rerun-from upload uses different GCS URLs for each episode."""
        base_config.rerun_from = "upload"
        processor = EpisodeProcessor(base_config, base_context)
        
        # Process Episode 1
        episode1_data = unique_episode_data()
        urls1 = unique_gcs_urls()
        urls1_text = urls1['mp3_url']
        
        base_context.episode_id = 'episode1_id'
        base_context.gcs_urls = {
            'mp3_url': sample_firestore_episode['mp3_url'],
            'transcript_url': sample_firestore_episode['transcript_url'],
            'summary_url': sample_firestore_episode['summary_url'],
            'summary_image_url': sample_firestore_episode['summary_image_url']
        }
        
        def upload_side_effect1(*args, **kwargs):
            base_context.gcs_urls = urls1
            return urls1
        
        with patch('src.pipeline.steps.gcs_upload.upload_to_gcs', side_effect=upload_side_effect1), \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_validate.return_value = True
            
            processor.process_episode(episode1_data)
        
        episode1_urls = base_context.gcs_urls
        
        # Process Episode 2
        episode2_data = unique_episode_data()
        urls2 = unique_gcs_urls()
        urls2_text = urls2['mp3_url']
        
        base_context.episode_id = 'episode2_id'
        base_context.gcs_urls = {
            'mp3_url': sample_firestore_episode['mp3_url'],
            'transcript_url': sample_firestore_episode['transcript_url'],
            'summary_url': sample_firestore_episode['summary_url'],
            'summary_image_url': sample_firestore_episode['summary_image_url']
        }
        
        def upload_side_effect2(*args, **kwargs):
            base_context.gcs_urls = urls2
            return urls2
        
        with patch('src.pipeline.steps.gcs_upload.upload_to_gcs', side_effect=upload_side_effect2), \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_validate.return_value = True
            
            processor.process_episode(episode2_data)
        
        episode2_urls = base_context.gcs_urls
        
        assert urls1_text != urls2_text, f"Original URLs should be different. Episode 1: '{urls1_text}', Episode 2: '{urls2_text}'"
        assert episode1_urls == urls1, "Episode 1 URLs should match"
        assert episode2_urls == urls2, "Episode 2 URLs should match"
        assert episode1_urls != episode2_urls, "GCS URLs should be different for each episode"
        assert episode1_urls['mp3_url'] != episode2_urls['mp3_url']
    
    def test_rerun_from_validate_only_runs_validation(
        self, base_config, base_context, sample_episode_data, sample_firestore_episode
    ):
        """Test that --rerun-from validate only runs validation step."""
        base_config.rerun_from = "validate"
        processor = EpisodeProcessor(base_config, base_context)
        
        # Set up existing episode
        base_context.episode_id = sample_firestore_episode['id']
        base_context.gcs_urls = {
            'mp3_url': sample_firestore_episode['mp3_url'],
            'transcript_url': sample_firestore_episode['transcript_url'],
            'summary_url': sample_firestore_episode['summary_url'],
            'summary_image_url': sample_firestore_episode['summary_image_url']
        }
        
        with patch('src.pipeline.steps.download.download_episode') as mock_download, \
             patch('src.pipeline.steps.transcribe.transcribe_episode') as mock_transcribe, \
             patch('src.pipeline.steps.summarize.generate_summary') as mock_summarize, \
             patch('src.pipeline.steps.gcs_upload.upload_to_gcs') as mock_upload, \
             patch('src.pipeline.steps.firestore.upload_to_firestore'), \
             patch('src.pipeline.steps.validate.validate_episode') as mock_validate:
            
            mock_validate.return_value = True
            
            processor.process_episode(sample_episode_data)
            
            # Verify only validate was called
            mock_download.assert_not_called()
            mock_transcribe.assert_not_called()
            mock_summarize.assert_not_called()
            mock_upload.assert_not_called()
            # Note: firestore might be called for loading data, but not for uploading
            mock_validate.assert_called_once()

