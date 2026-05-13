"""
Shared pytest fixtures for podcast downloader tests.
"""

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.podcast_models import Sentence
from src.pipeline import PipelineConfig
from src.pipeline import ServiceContainer as PipelineContext

# Load test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir():
    """Return path to fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_podcasts():
    """Load sample podcast configuration."""
    with open(FIXTURES_DIR / "sample_podcasts.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_episodes():
    """Load sample episode data from API."""
    with open(FIXTURES_DIR / "sample_episodes.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def sample_firestore_episodes():
    """Load sample Firestore episode documents."""
    with open(FIXTURES_DIR / "sample_firestore_episodes.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def test_mp3_files(tmp_path):
    """Create small test MP3 files for integration tests."""
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    
    # Copy test MP3 files from fixtures
    source_episode1 = FIXTURES_DIR / "audio" / "episode1.mp3"
    source_episode2 = FIXTURES_DIR / "audio" / "episode2.mp3"
    
    episode1_mp3 = audio_dir / "episode1.mp3"
    episode2_mp3 = audio_dir / "episode2.mp3"
    
    if source_episode1.exists():
        shutil.copy(source_episode1, episode1_mp3)
    else:
        # Create minimal MP3 file if fixture doesn't exist
        episode1_mp3.write_bytes(b'ID3\x03\x00' + b'\x00' * 100000)
    
    if source_episode2.exists():
        shutil.copy(source_episode2, episode2_mp3)
    else:
        # Create minimal MP3 file if fixture doesn't exist
        episode2_mp3.write_bytes(b'ID3\x03\x00' + b'\x01' * 100000)
    
    return {
        'episode1': episode1_mp3,
        'episode2': episode2_mp3
    }


@pytest.fixture
def mock_firebase_service():
    """Mock FirebaseService for testing."""
    mock = MagicMock()
    
    # Default behavior: episode doesn't exist
    mock.get_episode_by_fields.return_value = None
    mock.get_all_episodes.return_value = []
    mock.get_episode_by_id.return_value = None
    mock.episode_exists.return_value = False
    mock.get_existing_episode_titles.return_value = set()
    mock.get_existing_episode_numbers.return_value = set()
    mock.episode_exists_in_tag.return_value = False
    mock.episode_exists_in_ticker.return_value = False
    mock.validate_episode_in_tags_and_tickers.return_value = {
        'tags_valid': True,
        'tickers_valid': True,
        'tags_details': {},
        'tickers_details': {}
    }
    
    return mock


@pytest.fixture
def mock_gcs_service():
    """Mock GCSStorageService for testing."""
    mock = MagicMock()
    
    # Default GCS URLs
    default_urls = {
        'mp3_url': 'gs://test-bucket/mp3/podcast/episode.mp3',
        'transcript_url': 'gs://test-bucket/transcripts/podcast/episode.json',
        'summary_url': 'gs://test-bucket/summaries/podcast/episode.md',
        'summary_image_url': 'gs://test-bucket/images/podcast/episode.svg',
        'mp3_public_url': 'https://storage.googleapis.com/test-bucket/mp3/podcast/episode.mp3',
        'transcript_public_url': 'https://storage.googleapis.com/test-bucket/transcripts/podcast/episode.json',
        'summary_public_url': 'https://storage.googleapis.com/test-bucket/summaries/podcast/episode.md',
        'summary_image_public_url': 'https://storage.googleapis.com/test-bucket/images/podcast/episode.svg',
    }
    
    mock.upload_episode_files.return_value = default_urls
    mock.upload_file_from_string.return_value = (True, default_urls['summary_url'])
    mock.download_transcript_by_gcs_url.return_value = {
        'text': 'Test transcript text',
        'sentences': [
            {'index': 0, 'content': 'Test sentence 1', 'start': 0, 'end': 1000}
        ],
        'words': None
    }
    mock.download_text_by_gcs_url.return_value = 'Test summary text'
    mock.download_file_by_gcs_url.return_value = Path('/tmp/test.mp3')
    mock.generate_public_url.return_value = 'https://storage.googleapis.com/test-bucket/path'
    mock.bucket = MagicMock()
    mock.bucket.blob.return_value.exists.return_value = True
    mock.bucket_name = 'test-bucket'
    
    return mock


@pytest.fixture
def mock_stt_service():
    """Mock SpeechToTextService for testing."""
    mock = MagicMock()
    
    # Default transcript result
    default_transcript = {
        'text': 'Test transcript text',
        'sentences': [
            Sentence(index=0, content='Test sentence 1', start=0, end=1000),
            Sentence(index=1, content='Test sentence 2', start=1000, end=2000),
        ],
        'words': None
    }
    
    mock.transcribe.return_value = default_transcript
    mock.get_service_name.return_value = 'MockSTT'
    mock.model = None
    
    return mock


@pytest.fixture
def mock_summarize_service():
    """Mock SummarizeService for testing."""
    mock = MagicMock()
    
    # Default summary result
    default_summary = {
        'summary_text': 'Test summary text',
        'svg_content': '<svg>Test SVG</svg>',
        'events_markdown': '# Events\nTest events',
        'related_tickers': ['AAPL', 'GOOGL']
    }
    
    mock.generate_summary_from_text.return_value = default_summary
    
    return mock


@pytest.fixture
def base_config(tmp_path):
    """Create base PipelineConfig for testing."""
    return PipelineConfig(
        config_file=Path("podcasts_to_download.json"),
        podcast_name="Test Podcast",
        podcast_link="https://podcasttomp3.com/podcasts/v2/123456",
        spotify_show_link=None,
        episode_limit=2,
        stt_service_name="groq",
        stt_model=None,
        rerun_from=None,
        reuse_existing_transcript=False,
        use_file_mode=False,
        fill_limit=False,
        temp_dir=tmp_path / "temp"
    )


@pytest.fixture
def base_context(mock_firebase_service, mock_gcs_service, mock_stt_service, mock_summarize_service):
    """Create base PipelineContext with mocked services."""
    context = PipelineContext()
    context.firebase_service = mock_firebase_service
    context.gcs_service = mock_gcs_service
    context.stt_service = mock_stt_service
    context.summarize_service = mock_summarize_service
    return context


@pytest.fixture
def sample_episode_data(sample_episodes):
    """Get first episode from sample episodes."""
    return sample_episodes[0]


@pytest.fixture
def sample_firestore_episode(sample_firestore_episodes):
    """Get first episode from sample Firestore episodes."""
    return sample_firestore_episodes[0]


@pytest.fixture
def episode_processor(base_config, base_context):
    """Create EpisodeProcessor instance for testing."""
    from src.pipeline import EpisodeProcessor
    return EpisodeProcessor(base_config, base_context)


@pytest.fixture
def mock_download_file(monkeypatch):
    """Mock download_file function to avoid actual downloads."""
    def mock_download(url, filepath, episode_title, **kwargs):
        # Create a dummy file
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(b'fake mp3 content')
        return True
    
    monkeypatch.setattr('src.service.download_podcasts.download_file', mock_download)
    monkeypatch.setattr('src.service.download_podcasts.download_file_to_temp', 
                       lambda url, title, temp_dir=None, **kwargs: Path(temp_dir) / f"{title}.mp3" if temp_dir else Path(f"/tmp/{title}.mp3"))


@pytest.fixture
def mock_fetch_episodes(monkeypatch, sample_episodes):
    """Mock fetch_episodes to return sample episodes."""
    def mock_fetch(podcast_id):
        return sample_episodes
    
    monkeypatch.setattr('src.service.download_podcasts.fetch_episodes', mock_fetch)
    return mock_fetch


@pytest.fixture
def unique_episode_data():
    """Generate unique episode data for testing context clearing."""
    episode_counter = {'count': 0}
    
    def _generate_episode():
        episode_counter['count'] += 1
        num = episode_counter['count']
        return {
            'title': f'Episode {num}: Test Title',
            'episodeNumber': num,
            'episodeUrl': f'https://example.com/episode{num}.mp3',
            'description': f'Description for episode {num}',
            'publishedAt': f'2024-01-{num:02d}T00:00:00Z'
        }
    
    return _generate_episode


@pytest.fixture
def unique_transcript_data():
    """Generate unique transcript data for testing context clearing."""
    transcript_counter = {'count': 0}
    
    def _generate_transcript():
        transcript_counter['count'] += 1
        num = transcript_counter['count']
        return {
            'text': f'This is transcript text for episode {num}. It contains unique content.',
            'sentences': [
                Sentence(index=0, content=f'Sentence 1 for episode {num}.', start=0, end=1000),
                Sentence(index=1, content=f'Sentence 2 for episode {num}.', start=1000, end=2000),
            ],
            'words': None
        }
    
    return _generate_transcript


@pytest.fixture
def unique_summary_data():
    """Generate unique summary data for testing context clearing."""
    summary_counter = {'count': 0}
    
    def _generate_summary():
        summary_counter['count'] += 1
        num = summary_counter['count']
        return {
            'summary_text': f'Summary for episode {num}. This is unique content.',
            'svg_content': f'<svg>Episode {num} SVG</svg>',
            'events_markdown': f'# Events for Episode {num}\nTest events content.',
            'related_tickers': [f'TICK{num}']
        }
    
    return _generate_summary


@pytest.fixture
def unique_gcs_urls():
    """Generate unique GCS URLs for testing context clearing."""
    url_counter = {'count': 0}
    
    def _generate_urls():
        url_counter['count'] += 1
        num = url_counter['count']
        return {
            'mp3_url': f'gs://test-bucket/mp3/podcast/episode{num}.mp3',
            'transcript_url': f'gs://test-bucket/transcripts/podcast/episode{num}.json',
            'summary_url': f'gs://test-bucket/summaries/podcast/episode{num}.md',
            'summary_image_url': f'gs://test-bucket/images/podcast/episode{num}.svg',
            'mp3_public_url': f'https://storage.googleapis.com/test-bucket/mp3/podcast/episode{num}.mp3',
            'transcript_public_url': f'https://storage.googleapis.com/test-bucket/transcripts/podcast/episode{num}.json',
            'summary_public_url': f'https://storage.googleapis.com/test-bucket/summaries/podcast/episode{num}.md',
            'summary_image_public_url': f'https://storage.googleapis.com/test-bucket/images/podcast/episode{num}.svg',
        }
    
    return _generate_urls

