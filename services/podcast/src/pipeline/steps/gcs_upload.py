"""
Step 4: Upload to GCS

This module handles uploading episode files to Google Cloud Storage.
"""

import json

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import generate_episode_id


def upload_to_gcs(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> None:
    """
    Upload episode files to Google Cloud Storage.
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
    """
    # Determine if we should upload
    # Skip if rerun_from is "validate"
    should_upload = config.rerun_from in [None, "download", "transcribe", "summarize", "upload"]
    
    if not should_upload:
        return
    
    # Check if already uploaded (idempotency)
    # For rerun_from="summarize", we may have partial URLs (MP3, transcript)
    # but need to regenerate summary URLs, so check if we have all required URLs
    # For rerun_from="transcribe", we want to re-upload transcript as JSON (even if .txt exists)
    if episode_data.gcs_urls:
        required_urls = ['mp3_url', 'transcript_url', 'summary_url', 'summary_image_url']
        has_all_urls = all(episode_data.gcs_urls.get(url) for url in required_urls)
        
        # For rerun_from="download", we always want to re-upload everything (treating as new)
        # For rerun_from="transcribe", we always want to re-upload transcript as JSON
        # (even if it's already JSON, to ensure it has the latest transcription)
        needs_transcript_reupload = config.rerun_from == "transcribe" and episode_data.transcript_text
        is_download_rerun = config.rerun_from == "download"
        
        # If we have all URLs and we're not rerunning from download, summarize, or transcribe, skip upload
        if has_all_urls and not is_download_rerun and config.rerun_from != "summarize" and not needs_transcript_reupload:
            return
        
        # For rerun_from="summarize", if we're missing summary URLs, we need to upload
        # Merge existing URLs with new ones
        if config.rerun_from == "summarize" and not has_all_urls:
            # We'll merge the new URLs with existing ones below
            pass
        elif has_all_urls and not is_download_rerun and not needs_transcript_reupload:
            return
    
    # Need GCS service
    if not services.gcs_service:
        print("  ⚠ Warning: GCS service not available, skipping GCS upload")
        return
    
    # Need episode ID
    if not episode_data.episode_id:
        if not services.firebase_service:
            raise ValueError("Firebase service not initialized (needed for episode ID generation)")
        # Generate episode ID
        episode_data.episode_id = generate_episode_id(
            services.firebase_service,
            episode_data.podcast_name,
            episode_data.api_data,
            episode_data.summary_result
        )
    
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    print(f"  ☁️  Uploading files to GCS: {episode_title}")
    
    # For rerun_from="download", we want to upload all files (treating each episode as new, force re-upload)
    # For rerun_from="summarize", we only want to upload summary files (force re-upload)
    # For rerun_from="transcribe", we want to upload all files (transcript, summary, events, etc.) since transcript changed
    # For other modes, upload all files with skip_existing=True
    if config.rerun_from == "download":
        # For rerun_from="download", upload all files and force re-upload (skip_existing=False)
        # This treats each episode as new and ensures all files are re-uploaded
        # Prepare transcript data dict with text, sentences, and words
        transcript_data = None
        if episode_data.transcript_text:
            # Convert sentences to list of dicts if needed
            sentences_data = None
            if episode_data.transcript_sentences:
                from src.models.podcast_models import Sentence
                sentences_data = [
                    {
                        "index": s.index,
                        "content": s.content,
                        "start": s.start,
                        "end": s.end
                    } if isinstance(s, Sentence) else s
                    for s in episode_data.transcript_sentences
                ]
            
            transcript_data = {
                "text": episode_data.transcript_text,
                "sentences": sentences_data,
                "words": episode_data.transcript_words  # Deprecated, kept for backward compatibility
            }
        
        # Upload all files with skip_existing=False to force re-upload
        gcs_urls = services.gcs_service.upload_episode_files(
            episode_id=episode_data.episode_id,
            podcast_name=episode_data.podcast_name,
            mp3_path=episode_data.mp3_path,
            transcript_data=transcript_data,
            summary_content=episode_data.summary_result.get('summary_text') if episode_data.summary_result else None,
            svg_content=episode_data.summary_result.get('svg_content') if episode_data.summary_result else None,
            events_markdown_content=episode_data.summary_result.get('events_markdown') if episode_data.summary_result else None,
            sentences_markdown_content=episode_data.summary_result.get('sentences_markdown') if episode_data.summary_result else None,
            pptx_base64=episode_data.summary_result.get('pptx_base64') if episode_data.summary_result else None,
            marp_markdown_content=episode_data.summary_result.get('marp_markdown') if episode_data.summary_result else None,
            ticker_recommendations_data=episode_data.summary_result.get('ticker_recommendations') if episode_data.summary_result else None,
            ticker_marp_markdown_content=episode_data.summary_result.get('ticker_marp_markdown') if episode_data.summary_result else None,
            skip_existing=False  # Force re-upload of all files including MP3
        )
    elif config.rerun_from == "summarize" and episode_data.summary_result:
        # Only upload summary files, force re-upload (skip_existing=False)
        gcs_urls = {
            'mp3_url': episode_data.gcs_urls.get('mp3_url') if episode_data.gcs_urls else None,
            'mp3_public_url': episode_data.gcs_urls.get('mp3_public_url') if episode_data.gcs_urls else None,
            'transcript_url': episode_data.gcs_urls.get('transcript_url') if episode_data.gcs_urls else None,
            'transcript_public_url': episode_data.gcs_urls.get('transcript_public_url') if episode_data.gcs_urls else None,
            'summary_url': None,
            'summary_public_url': None,
            'summary_image_url': None,
            'summary_image_public_url': None,
        }
        
        # Force upload summary files (skip_existing=False to overwrite old content)
        summary_text = episode_data.summary_result.get('summary_text')
        svg_content = episode_data.summary_result.get('svg_content')
        events_markdown = episode_data.summary_result.get('events_markdown')
        sentences_markdown = episode_data.summary_result.get('sentences_markdown')
        pptx_base64 = episode_data.summary_result.get('pptx_base64')
        marp_markdown = episode_data.summary_result.get('marp_markdown')
        
        if summary_text:
            success, summary_url = services.gcs_service.upload_file_from_string(
                summary_text, 'summaries', episode_data.podcast_name, episode_data.episode_id, 'md', skip_existing=False
            )
            if success and summary_url:
                gcs_urls['summary_url'] = summary_url
                blob_path = summary_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['summary_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded summary to GCS ({len(summary_text):,} characters)")
        
        if events_markdown:
            success, events_url = services.gcs_service.upload_file_from_string(
                events_markdown, 'events', episode_data.podcast_name, episode_data.episode_id, 'md', skip_existing=False
            )
            if success and events_url:
                gcs_urls['events_markdown_url'] = events_url
                blob_path = events_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['events_markdown_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded events markdown to GCS ({len(events_markdown):,} characters)")
        
        if sentences_markdown:
            success, sentences_url = services.gcs_service.upload_file_from_string(
                sentences_markdown, 'sentences', episode_data.podcast_name, episode_data.episode_id, 'md', skip_existing=False
            )
            if success and sentences_url:
                gcs_urls['sentences_markdown_url'] = sentences_url
                blob_path = sentences_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['sentences_markdown_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded sentences markdown to GCS ({len(sentences_markdown):,} characters)")
        
        if svg_content:
            success, svg_url = services.gcs_service.upload_file_from_string(
                svg_content, 'images', episode_data.podcast_name, episode_data.episode_id, 'svg', skip_existing=False
            )
            if success and svg_url:
                gcs_urls['summary_image_url'] = svg_url
                blob_path = svg_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['summary_image_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print("  ✓ Re-uploaded SVG to GCS")
        
        if pptx_base64:
            success, pptx_url = services.gcs_service.upload_file_from_base64(
                pptx_base64, 'presentations', episode_data.podcast_name, episode_data.episode_id, 'pptx', skip_existing=False
            )
            if success and pptx_url:
                gcs_urls['pptx_url'] = pptx_url
                blob_path = pptx_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['pptx_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print("  ✓ Re-uploaded PPTX to GCS")
        
        if marp_markdown:
            success, marp_url = services.gcs_service.upload_file_from_string(
                marp_markdown, 'marp', episode_data.podcast_name, episode_data.episode_id, 'md', skip_existing=False
            )
            if success and marp_url:
                gcs_urls['marp_markdown_url'] = marp_url
                blob_path = marp_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['marp_markdown_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded marp markdown to GCS ({len(marp_markdown):,} characters)")
        
        ticker_recommendations = episode_data.summary_result.get('ticker_recommendations') if episode_data.summary_result else None
        if ticker_recommendations:
            ticker_recommendations_json = json.dumps(ticker_recommendations, ensure_ascii=False, indent=2)
            success, ticker_recommendations_url = services.gcs_service.upload_file_from_string(
                ticker_recommendations_json, 'ticker_recommendations', episode_data.podcast_name, episode_data.episode_id, 'json', skip_existing=False
            )
            if success and ticker_recommendations_url:
                gcs_urls['ticker_recommendations_url'] = ticker_recommendations_url
                blob_path = ticker_recommendations_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['ticker_recommendations_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print("  ✓ Re-uploaded ticker recommendations to GCS")
        
        ticker_marp_markdown = episode_data.summary_result.get('ticker_marp_markdown') if episode_data.summary_result else None
        if ticker_marp_markdown:
            success, ticker_marp_url = services.gcs_service.upload_file_from_string(
                ticker_marp_markdown, 'ticker_marp', episode_data.podcast_name, episode_data.episode_id, 'md', skip_existing=False
            )
            if success and ticker_marp_url:
                gcs_urls['ticker_marp_markdown_url'] = ticker_marp_url
                blob_path = ticker_marp_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                gcs_urls['ticker_marp_markdown_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded ticker marp markdown to GCS ({len(ticker_marp_markdown):,} characters)")
    elif config.rerun_from == "transcribe":
        # For rerun_from="transcribe", upload transcript and derived files (summary, events, etc.)
        # but preserve existing MP3 URL since the MP3 file hasn't changed
        # Prepare transcript data dict with text, sentences, and words
        transcript_data = None
        if episode_data.transcript_text:
            # Convert sentences to list of dicts if needed
            sentences_data = None
            if episode_data.transcript_sentences:
                from src.models.podcast_models import Sentence
                sentences_data = [
                    {
                        "index": s.index,
                        "content": s.content,
                        "start": s.start,
                        "end": s.end
                    } if isinstance(s, Sentence) else s
                    for s in episode_data.transcript_sentences
                ]
            
            transcript_data = {
                "text": episode_data.transcript_text,
                "sentences": sentences_data,
                "words": episode_data.transcript_words  # Deprecated, kept for backward compatibility
            }
        
        # Upload transcript as JSON (force re-upload)
        if transcript_data:
            transcript_json = json.dumps(transcript_data, ensure_ascii=False, indent=2)
            success, transcript_url = services.gcs_service.upload_file_from_string(
                transcript_json, 'transcripts', episode_data.podcast_name, episode_data.episode_id, 'json', skip_existing=False
            )
            if success and transcript_url:
                # Update episode_data.gcs_urls with new JSON transcript URL
                if not episode_data.gcs_urls:
                    episode_data.gcs_urls = {}
                episode_data.gcs_urls['transcript_url'] = transcript_url
                blob_path = transcript_url.replace(f"gs://{services.gcs_service.bucket_name}/", "")
                episode_data.gcs_urls['transcript_public_url'] = services.gcs_service.generate_public_url(blob_path)
                print(f"  ✓ Re-uploaded transcript as JSON to GCS ({len(episode_data.transcript_text):,} characters)")
        
        # Upload derived files (summary, events, sentences, SVG) - force re-upload (skip_existing=False)
        # But skip MP3 upload - preserve existing MP3 URL since the file hasn't changed
        gcs_urls = {
            'mp3_url': episode_data.gcs_urls.get('mp3_url') if episode_data.gcs_urls else None,
            'mp3_public_url': episode_data.gcs_urls.get('mp3_public_url') if episode_data.gcs_urls else None,
            'transcript_url': episode_data.gcs_urls.get('transcript_url') if episode_data.gcs_urls else None,
            'transcript_public_url': episode_data.gcs_urls.get('transcript_public_url') if episode_data.gcs_urls else None,
        }
        
        # Upload only derived files (summary, events, sentences, SVG) - skip MP3
        derived_urls = services.gcs_service.upload_episode_files(
            episode_id=episode_data.episode_id,
            podcast_name=episode_data.podcast_name,
            mp3_path=None,  # Skip MP3 upload - preserve existing URL
            transcript_data=None,  # Already uploaded above
            summary_content=episode_data.summary_result.get('summary_text') if episode_data.summary_result else None,
            svg_content=episode_data.summary_result.get('svg_content') if episode_data.summary_result else None,
            events_markdown_content=episode_data.summary_result.get('events_markdown') if episode_data.summary_result else None,
            sentences_markdown_content=episode_data.summary_result.get('sentences_markdown') if episode_data.summary_result else None,
            pptx_base64=episode_data.summary_result.get('pptx_base64') if episode_data.summary_result else None,
            marp_markdown_content=episode_data.summary_result.get('marp_markdown') if episode_data.summary_result else None,
            ticker_recommendations_data=episode_data.summary_result.get('ticker_recommendations') if episode_data.summary_result else None,
            ticker_marp_markdown_content=episode_data.summary_result.get('ticker_marp_markdown') if episode_data.summary_result else None,
            skip_existing=False  # Force re-upload of derived files
        )
        
        # Merge derived file URLs with preserved MP3 and transcript URLs
        gcs_urls.update({
            'summary_url': derived_urls.get('summary_url'),
            'summary_public_url': derived_urls.get('summary_public_url'),
            'summary_image_url': derived_urls.get('summary_image_url'),
            'summary_image_public_url': derived_urls.get('summary_image_public_url'),
            'events_markdown_url': derived_urls.get('events_markdown_url'),
            'events_markdown_public_url': derived_urls.get('events_markdown_public_url'),
            'sentences_markdown_url': derived_urls.get('sentences_markdown_url'),
            'sentences_markdown_public_url': derived_urls.get('sentences_markdown_public_url'),
            'pptx_url': derived_urls.get('pptx_url'),
            'pptx_public_url': derived_urls.get('pptx_public_url'),
            'marp_markdown_url': derived_urls.get('marp_markdown_url'),
            'marp_markdown_public_url': derived_urls.get('marp_markdown_public_url'),
            'ticker_recommendations_url': derived_urls.get('ticker_recommendations_url'),
            'ticker_recommendations_public_url': derived_urls.get('ticker_recommendations_public_url'),
            'ticker_marp_markdown_url': derived_urls.get('ticker_marp_markdown_url'),
            'ticker_marp_markdown_public_url': derived_urls.get('ticker_marp_markdown_public_url'),
        })
        
        # Use the transcript URL we uploaded above
        if episode_data.gcs_urls and episode_data.gcs_urls.get('transcript_url'):
            gcs_urls['transcript_url'] = episode_data.gcs_urls.get('transcript_url')
            gcs_urls['transcript_public_url'] = episode_data.gcs_urls.get('transcript_public_url')
    else:
        # Normal upload: upload all files with skip_existing=True
        # Prepare transcript data dict with text, sentences, and words
        transcript_data = None
        if episode_data.transcript_text:
            # Convert sentences to list of dicts if needed
            sentences_data = None
            if episode_data.transcript_sentences:
                from src.models.podcast_models import Sentence
                sentences_data = [
                    {
                        "index": s.index,
                        "content": s.content,
                        "start": s.start,
                        "end": s.end
                    } if isinstance(s, Sentence) else s
                    for s in episode_data.transcript_sentences
                ]
            
            transcript_data = {
                "text": episode_data.transcript_text,
                "sentences": sentences_data,
                "words": episode_data.transcript_words  # Deprecated, kept for backward compatibility
            }
        
        gcs_urls = services.gcs_service.upload_episode_files(
            episode_id=episode_data.episode_id,
            podcast_name=episode_data.podcast_name,
            mp3_path=episode_data.mp3_path,
            transcript_data=transcript_data,
            summary_content=episode_data.summary_result.get('summary_text') if episode_data.summary_result else None,
            svg_content=episode_data.summary_result.get('svg_content') if episode_data.summary_result else None,
            events_markdown_content=episode_data.summary_result.get('events_markdown') if episode_data.summary_result else None,
            sentences_markdown_content=episode_data.summary_result.get('sentences_markdown') if episode_data.summary_result else None,
            pptx_base64=episode_data.summary_result.get('pptx_base64') if episode_data.summary_result else None,
            marp_markdown_content=episode_data.summary_result.get('marp_markdown') if episode_data.summary_result else None,
            ticker_recommendations_data=episode_data.summary_result.get('ticker_recommendations') if episode_data.summary_result else None,
            ticker_marp_markdown_content=episode_data.summary_result.get('ticker_marp_markdown') if episode_data.summary_result else None,
            skip_existing=True
        )
    
    # Merge with existing URLs if we had partial URLs (e.g., from rerun_from="summarize")
    if episode_data.gcs_urls and config.rerun_from == "summarize":
        # Preserve existing MP3 and transcript URLs, use new summary URLs
        episode_data.gcs_urls.update({
            'summary_url': gcs_urls.get('summary_url'),
            'summary_image_url': gcs_urls.get('summary_image_url'),
            'summary_public_url': gcs_urls.get('summary_public_url'),
            'summary_image_public_url': gcs_urls.get('summary_image_public_url'),
            'events_markdown_url': gcs_urls.get('events_markdown_url'),
            'events_markdown_public_url': gcs_urls.get('events_markdown_public_url'),
            'sentences_markdown_url': gcs_urls.get('sentences_markdown_url'),
            'sentences_markdown_public_url': gcs_urls.get('sentences_markdown_public_url'),
            'pptx_url': gcs_urls.get('pptx_url'),
            'pptx_public_url': gcs_urls.get('pptx_public_url'),
            'marp_markdown_url': gcs_urls.get('marp_markdown_url'),
            'marp_markdown_public_url': gcs_urls.get('marp_markdown_public_url'),
            'ticker_recommendations_url': gcs_urls.get('ticker_recommendations_url'),
            'ticker_recommendations_public_url': gcs_urls.get('ticker_recommendations_public_url'),
            'ticker_marp_markdown_url': gcs_urls.get('ticker_marp_markdown_url'),
            'ticker_marp_markdown_public_url': gcs_urls.get('ticker_marp_markdown_public_url'),
        })
    else:
        episode_data.gcs_urls = gcs_urls
    
    print("  ✓ Files uploaded to GCS")
