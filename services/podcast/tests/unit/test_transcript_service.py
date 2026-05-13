"""
Unit tests for transcript service initialization and configuration.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from src.pipeline import PipelineConfig
from src.pipeline.steps.initialize import initialize_stt_service


@pytest.mark.unit
class TestTranscriptService:
    """Test transcript service initialization."""
    
    @patch('src.service.speech_to_text.GroqService')
    def test_initialize_groq_service(self, mock_groq_class):
        """Test initializing GroqService."""
        mock_service = MagicMock()
        mock_service.get_service_name.return_value = 'Groq'
        mock_groq_class.return_value = mock_service
        
        config = PipelineConfig(
            config_file=Path("test.json"),
            podcast_name="Test",
            podcast_link="https://test.com",
            stt_service_name="groq",
            stt_model=None
        )
        
        service = initialize_stt_service(config)
        
        assert service == mock_service
        mock_groq_class.assert_called_once()
    
    @patch('src.service.speech_to_text.GroqService')
    def test_initialize_groq_service_with_model(self, mock_groq_class):
        """Test initializing GroqService with specific model."""
        mock_service = MagicMock()
        mock_service.get_service_name.return_value = 'Groq'
        mock_groq_class.return_value = mock_service
        
        config = PipelineConfig(
            config_file=Path("test.json"),
            podcast_name="Test",
            podcast_link="https://test.com",
            stt_service_name="groq",
            stt_model="whisper-large-v3"
        )
        
        service = initialize_stt_service(config)
        
        assert service == mock_service
        mock_groq_class.assert_called_once_with(model="whisper-large-v3")
    
    @patch('src.service.speech_to_text.WhisperService')
    def test_initialize_whisper_service(self, mock_whisper_class):
        """Test initializing WhisperService."""
        mock_service = MagicMock()
        mock_service.get_service_name.return_value = 'Whisper'
        mock_whisper_class.return_value = mock_service
        
        config = PipelineConfig(
            config_file=Path("test.json"),
            podcast_name="Test",
            podcast_link="https://test.com",
            stt_service_name="whisper",
            stt_model=None
        )
        
        service = initialize_stt_service(config)
        
        assert service == mock_service
        mock_whisper_class.assert_called_once()
    
    @patch('src.service.speech_to_text.WhisperService')
    def test_initialize_openai_service_maps_to_whisper(self, mock_whisper_class):
        """Test that 'openai' service name maps to WhisperService."""
        mock_service = MagicMock()
        mock_service.get_service_name.return_value = 'Whisper'
        mock_whisper_class.return_value = mock_service
        
        config = PipelineConfig(
            config_file=Path("test.json"),
            podcast_name="Test",
            podcast_link="https://test.com",
            stt_service_name="openai",
            stt_model=None
        )
        
        service = initialize_stt_service(config)
        
        assert service == mock_service
        mock_whisper_class.assert_called_once()
    
    @patch('src.service.speech_to_text.WhisperService')
    def test_unknown_service_defaults_to_whisper(self, mock_whisper_class):
        """Test that unknown service name defaults to WhisperService."""
        mock_service = MagicMock()
        mock_service.get_service_name.return_value = 'Whisper'
        mock_whisper_class.return_value = mock_service
        
        config = PipelineConfig(
            config_file=Path("test.json"),
            podcast_name="Test",
            podcast_link="https://test.com",
            stt_service_name="unknown_service",
            stt_model=None
        )
        
        service = initialize_stt_service(config)
        
        assert service == mock_service
        mock_whisper_class.assert_called_once()

