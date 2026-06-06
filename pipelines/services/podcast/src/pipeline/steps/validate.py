"""
Step 6: Validate

This module handles validating that episodes were processed correctly.
"""

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import extract_tickers_from_markdown


def validate_episode(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> bool:
    """
    Validate that episode was processed correctly.
    
    Downloads and verifies content from GCS and Firestore to ensure data integrity.
    Stores validation results in episode_data.validation_results for later inspection.
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
        
    Returns:
        True if validation passes, False otherwise
    """
    # Initialize validation results
    episode_data.validation_results = {}
    
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    print(f"  🔍 Validating: {episode_title}")
    
    # Validate MP3 file exists (local or in episode_data)
    if episode_data.mp3_path:
        episode_data.validation_results['mp3_exists'] = episode_data.mp3_path.exists()
    else:
        episode_data.validation_results['mp3_exists'] = False
    
    # Validate transcript exists in episode_data
    if episode_data.transcript_text:
        episode_data.validation_results['transcript_exists'] = len(episode_data.transcript_text.strip()) > 0
    else:
        episode_data.validation_results['transcript_exists'] = False
    
    # Validate summary exists in episode_data
    if episode_data.summary_result:
        has_summary = bool(episode_data.summary_result.get('summary_text', '').strip())
        has_svg = bool(episode_data.summary_result.get('svg_content', '').strip())
        episode_data.validation_results['summary_exists'] = has_summary and has_svg
        
        # Validate that all tickers in related_tickers are present in summary text
        if episode_data.tickers and has_summary:
            summary_text = episode_data.summary_result.get('summary_text', '')
            tickers_in_summary = extract_tickers_from_markdown(summary_text)
            
            # Check if all tickers in episode_data.tickers are present in summary
            missing_tickers = []
            for ticker in episode_data.tickers:
                if ticker.upper() not in [t.upper() for t in tickers_in_summary]:
                    missing_tickers.append(ticker.upper())
            
            if missing_tickers:
                error_msg = (
                    f"\n{'='*80}\n"
                    f"VALIDATION ERROR: Ticker Mismatch Detected\n"
                    f"{'='*80}\n"
                    f"Episode: {episode_data.api_data.get('title', 'Unknown')}\n"
                    f"\n"
                    f"The following ticker(s) in related_tickers are NOT present in the summary text:\n"
                    f"  ❌ Missing tickers: {', '.join(missing_tickers)}\n"
                    f"\n"
                    f"Summary:\n"
                    f"  ✓ Tickers in related_tickers: {', '.join([t.upper() for t in episode_data.tickers])}\n"
                    f"  ✓ Tickers found in summary text: {', '.join([t.upper() for t in tickers_in_summary]) if tickers_in_summary else '(none)'}\n"
                    f"\n"
                    f"Expected: All tickers in related_tickers must appear as #ticker:SYMBOL in the summary.\n"
                    f"Example format: [Display Name](#ticker:SYMBOL) or #ticker:SYMBOL\n"
                    f"{'='*80}\n"
                )
                print(error_msg)
                episode_data.validation_results['tickers_in_summary_valid'] = False
                raise AssertionError(error_msg)
            else:
                episode_data.validation_results['tickers_in_summary_valid'] = True
                print(f"  ✓ All {len(episode_data.tickers)} ticker(s) in related_tickers are present in summary text")
        else:
            # No tickers to validate, or no summary text
            if not episode_data.tickers:
                episode_data.validation_results['tickers_in_summary_valid'] = None  # N/A
            else:
                episode_data.validation_results['tickers_in_summary_valid'] = False
    else:
        episode_data.validation_results['summary_exists'] = False
        episode_data.validation_results['tickers_in_summary_valid'] = False
    
    # Validate GCS URLs and download/verify content
    if episode_data.gcs_urls and services.gcs_service:
        required_urls = ['mp3_url', 'transcript_url', 'summary_url', 'summary_image_url']
        all_urls_present = all(episode_data.gcs_urls.get(url) for url in required_urls)
        episode_data.validation_results['gcs_urls_valid'] = all_urls_present
        
        if all_urls_present:
            # Download and verify transcript from GCS
            transcript_url = episode_data.gcs_urls.get('transcript_url')
            if transcript_url and episode_data.transcript_text:
                try:
                    # Use new download method that returns dict with text and words
                    downloaded_transcript_data = services.gcs_service.download_transcript_by_gcs_url(transcript_url)
                    downloaded_transcript_text = downloaded_transcript_data.get('text', '') if downloaded_transcript_data else ''
                    # Compare content (normalize whitespace for comparison)
                    local_transcript = episode_data.transcript_text.strip()
                    remote_transcript = downloaded_transcript_text.strip()
                    episode_data.validation_results['gcs_transcript_matches'] = (
                        len(local_transcript) > 0 and 
                        len(remote_transcript) > 0 and
                        abs(len(local_transcript) - len(remote_transcript)) < 100  # Allow small differences
                    )
                    if not episode_data.validation_results['gcs_transcript_matches']:
                        print(f"    ⚠ Transcript length mismatch: local={len(local_transcript)}, remote={len(remote_transcript)}")
                except Exception as e:
                    print(f"    ⚠ Warning: Could not download/verify transcript from GCS: {e}")
                    episode_data.validation_results['gcs_transcript_matches'] = False
            else:
                episode_data.validation_results['gcs_transcript_matches'] = False
            
            # Download and verify summary from GCS
            summary_url = episode_data.gcs_urls.get('summary_url')
            if summary_url and episode_data.summary_result:
                summary_text = episode_data.summary_result.get('summary_text', '').strip()
                if summary_text:
                    try:
                        downloaded_summary = services.gcs_service.download_text_by_gcs_url(summary_url)
                        # Compare content
                        local_summary = summary_text.strip()
                        remote_summary = downloaded_summary.strip()
                        episode_data.validation_results['gcs_summary_matches'] = (
                            len(local_summary) > 0 and 
                            len(remote_summary) > 0 and
                            abs(len(local_summary) - len(remote_summary)) < 100  # Allow small differences
                        )
                        if not episode_data.validation_results['gcs_summary_matches']:
                            print(f"    ⚠ Summary length mismatch: local={len(local_summary)}, remote={len(remote_summary)}")
                    except Exception as e:
                        print(f"    ⚠ Warning: Could not download/verify summary from GCS: {e}")
                        episode_data.validation_results['gcs_summary_matches'] = False
                else:
                    episode_data.validation_results['gcs_summary_matches'] = False
            else:
                episode_data.validation_results['gcs_summary_matches'] = False
            
            # Verify SVG exists in GCS (check if blob exists)
            svg_url = episode_data.gcs_urls.get('summary_image_url')
            if svg_url:
                try:
                    # Extract blob path from gs:// URL
                    if svg_url.startswith("gs://"):
                        without_scheme = svg_url[len("gs://"):]
                        parts = without_scheme.split("/", 1)
                        if len(parts) == 2:
                            bucket_name, blob_path = parts
                            # Access bucket through the service
                            bucket = services.gcs_service.bucket
                            blob = bucket.blob(blob_path)
                            episode_data.validation_results['gcs_svg_exists'] = blob.exists()
                            if not episode_data.validation_results['gcs_svg_exists']:
                                print(f"    ⚠ SVG file not found in GCS: {svg_url}")
                        else:
                            episode_data.validation_results['gcs_svg_exists'] = False
                    else:
                        episode_data.validation_results['gcs_svg_exists'] = False
                except Exception as e:
                    print(f"    ⚠ Warning: Could not verify SVG in GCS: {e}")
                    episode_data.validation_results['gcs_svg_exists'] = False
            else:
                episode_data.validation_results['gcs_svg_exists'] = False
            
            # Overall GCS validation
            episode_data.validation_results['gcs_files_accessible'] = (
                episode_data.validation_results.get('gcs_transcript_matches', False) and
                episode_data.validation_results.get('gcs_summary_matches', False) and
                episode_data.validation_results.get('gcs_svg_exists', False)
            )
        else:
            episode_data.validation_results['gcs_transcript_matches'] = False
            episode_data.validation_results['gcs_summary_matches'] = False
            episode_data.validation_results['gcs_svg_exists'] = False
            episode_data.validation_results['gcs_files_accessible'] = False
    else:
        episode_data.validation_results['gcs_urls_valid'] = False
        episode_data.validation_results['gcs_transcript_matches'] = False
        episode_data.validation_results['gcs_summary_matches'] = False
        episode_data.validation_results['gcs_svg_exists'] = False
        episode_data.validation_results['gcs_files_accessible'] = False
    
    # Validate Firestore document exists and verify content
    if services.firebase_service and episode_data.episode_id:
        exists = services.firebase_service.episode_exists(
            episode_data.podcast_name,
            episode_data.api_data.get('title'),
            episode_data.api_data.get('episodeNumber')
        )
        episode_data.validation_results['firestore_document_exists'] = exists
        
        if exists:
            # Get the actual document from Firestore and verify URLs match
            try:
                firestore_episode = services.firebase_service.get_episode_by_fields(
                    podcast_name=episode_data.podcast_name,
                    episode_title=episode_data.api_data.get('title'),
                    episode_number=episode_data.api_data.get('episodeNumber')
                )
                
                if firestore_episode and episode_data.gcs_urls:
                    # Verify GCS URLs match
                    url_matches = (
                        firestore_episode.get('transcript_url') == episode_data.gcs_urls.get('transcript_url') and
                        firestore_episode.get('summary_url') == episode_data.gcs_urls.get('summary_url') and
                        firestore_episode.get('summary_image_url') == episode_data.gcs_urls.get('summary_image_url')
                    )
                    episode_data.validation_results['firestore_urls_match'] = url_matches
                    
                    # Verify episode ID matches
                    episode_id_match = firestore_episode.get('id') == episode_data.episode_id
                    episode_data.validation_results['firestore_episode_id_matches'] = episode_id_match
                    
                    if not url_matches:
                        print("    ⚠ Firestore URLs don't match GCS URLs")
                    if not episode_id_match:
                        print(f"    ⚠ Firestore episode ID mismatch: stored={firestore_episode.get('id')}, expected={episode_data.episode_id}")
                else:
                    episode_data.validation_results['firestore_urls_match'] = False
                    episode_data.validation_results['firestore_episode_id_matches'] = False
            except Exception as e:
                print(f"    ⚠ Warning: Could not verify Firestore content: {e}")
                episode_data.validation_results['firestore_urls_match'] = False
                episode_data.validation_results['firestore_episode_id_matches'] = False
        else:
            print("    ⚠ Warning: Episode not found in Firestore after upload")
            episode_data.validation_results['firestore_urls_match'] = False
            episode_data.validation_results['firestore_episode_id_matches'] = False
    else:
        episode_data.validation_results['firestore_document_exists'] = False
        episode_data.validation_results['firestore_urls_match'] = False
        episode_data.validation_results['firestore_episode_id_matches'] = False
    
    # Validate episode exists in tags and tickers subcollections
    if services.firebase_service and episode_data.episode_id and (episode_data.tags or episode_data.tickers):
        try:
            validation_result = services.firebase_service.validate_episode_in_tags_and_tickers(
                episode_id=episode_data.episode_id,
                tags=episode_data.tags if episode_data.tags else [],
                tickers=episode_data.tickers if episode_data.tickers else []
            )
            
            episode_data.validation_results['tags_subcollections_valid'] = validation_result['tags_valid']
            episode_data.validation_results['tickers_subcollections_valid'] = validation_result['tickers_valid']
            
            # Log details for failed validations
            if not validation_result['tags_valid']:
                missing_tags = [tag for tag, exists in validation_result['tags_details'].items() if not exists]
                print(f"    ⚠ Episode missing from {len(missing_tags)} tag subcollections: {', '.join(missing_tags[:5])}{'...' if len(missing_tags) > 5 else ''}")
            
            if not validation_result['tickers_valid']:
                missing_tickers = [ticker for ticker, exists in validation_result['tickers_details'].items() if not exists]
                print(f"    ⚠ Episode missing from {len(missing_tickers)} ticker subcollections: {', '.join(missing_tickers[:5])}{'...' if len(missing_tickers) > 5 else ''}")
            
            if validation_result['tags_valid'] and validation_result['tickers_valid']:
                total = len(validation_result['tags_details']) + len(validation_result['tickers_details'])
                print(f"    ✓ Episode found in all {total} tag/ticker subcollections")
        except Exception as e:
            print(f"    ⚠ Warning: Could not validate tags/tickers subcollections: {e}")
            episode_data.validation_results['tags_subcollections_valid'] = False
            episode_data.validation_results['tickers_subcollections_valid'] = False
    else:
        # If no tags/tickers or no episode_id, mark as N/A (not applicable)
        if not episode_data.tags and not episode_data.tickers:
            episode_data.validation_results['tags_subcollections_valid'] = None  # N/A
            episode_data.validation_results['tickers_subcollections_valid'] = None  # N/A
        else:
            episode_data.validation_results['tags_subcollections_valid'] = False
            episode_data.validation_results['tickers_subcollections_valid'] = False
    
    # Overall validation result (check critical validations)
    critical_checks = [
        'transcript_exists',
        'summary_exists',
        'tickers_in_summary_valid',
        'gcs_urls_valid',
        'gcs_transcript_matches',
        'gcs_summary_matches',
        'gcs_svg_exists',
        'firestore_document_exists',
        'firestore_urls_match',
        'tags_subcollections_valid',
        'tickers_subcollections_valid',
    ]
    
    # Check critical validations (treat None as N/A and skip)
    critical_passed = all(
        episode_data.validation_results.get(check, False) is not False 
        for check in critical_checks
        if episode_data.validation_results.get(check) is not None  # Skip N/A checks
    )
    # For all_passed, only check non-None values
    all_passed = all(
        value is not False 
        for value in episode_data.validation_results.values() 
        if value is not None
    )
    
    if not critical_passed:
        print("  ⚠ Validation issues found:")
        for check in critical_checks:
            passed = episode_data.validation_results.get(check)
            if passed is False:
                print(f"    - {check}: FAILED")
            elif passed is None:
                print(f"    - {check}: N/A (no tags/tickers)")
        # Also show non-critical failures
        for check, passed in episode_data.validation_results.items():
            if check not in critical_checks and not passed:
                print(f"    - {check}: FAILED (non-critical)")
    else:
        print("  ✓ All critical validations passed")
        if not all_passed:
            print("  ⚠ Some non-critical validations failed (see details above)")
    
    return critical_passed
