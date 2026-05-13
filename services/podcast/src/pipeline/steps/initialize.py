"""
Step 0: Initialize Services

This module initializes all required services for the pipeline.
"""


from ..config import PipelineConfig
from ..service_container import ServiceContainer


def initialize_stt_service(config: PipelineConfig) -> object:
    """
    Initialize STT service based on config.
    
    Args:
        config: Pipeline configuration with stt_service_name and stt_model
        
    Returns:
        Initialized STT service instance
    """
    from src.service.speech_to_text import GroqService, WhisperService
    service_name_lower = config.stt_service_name.lower()
    if service_name_lower in ["whisper", "openai"]:
        return WhisperService()
    elif service_name_lower == "groq":
        # Use model from config if provided, otherwise default to "whisper-large-v3-turbo"
        model = config.stt_model if config.stt_model else "whisper-large-v3-turbo"
        return GroqService(model=model)
    else:
        # Default to Whisper if service name is not recognized
        print(f"⚠ Warning: Unknown STT service '{config.stt_service_name}', defaulting to Whisper")
        return WhisperService()


def initialize_services(config: PipelineConfig) -> ServiceContainer:
    """
    Initialize all required services based on config.
    
    All services are initialized at the beginning. If any required service fails,
    the pipeline will terminate with an error.
    
    Args:
        config: Pipeline configuration
        
    Returns:
        ServiceContainer with initialized services
        
    Raises:
        Exception: If any required service fails to initialize
    """
    services = ServiceContainer()
    errors = []
    
    # Initialize Firebase service (required for upload and validation)
    try:
        from src.service.upload_to_firebase import FirebaseService
        services.firebase_service = FirebaseService()
        print("✓ Firebase service initialized")
    except Exception as e:
        error_msg = f"Error initializing Firebase service: {e}"
        print(f"✗ {error_msg}")
        errors.append(error_msg)
    
    # Initialize STT service (required for transcription)
    try:
        services.stt_service = initialize_stt_service(config)
        service_info = f"{services.stt_service.get_service_name()}"
        if config.stt_model:
            service_info += f" (model: {config.stt_model})"
        print(f"✓ {service_info} service initialized")
    except Exception as e:
        error_msg = f"Error initializing speech-to-text service: {e}"
        print(f"✗ {error_msg}")
        errors.append(error_msg)
    
    # Initialize GCS service (required for upload and downloading transcripts)
    try:
        from src.service.gcs_storage_service import GCSStorageService
        services.gcs_service = GCSStorageService()
        print("✓ GCS storage service initialized")
    except Exception as e:
        error_msg = f"Error initializing GCS storage service: {e}"
        print(f"✗ {error_msg}")
        errors.append(error_msg)
    
    # Initialize Summarize service (required for summarization)
    try:
        from src.summarize import SummarizeService
        services.summarize_service = SummarizeService()
        print("✓ Summarize service initialized")
    except Exception as e:
        error_msg = f"Error initializing Summarize service: {e}"
        print(f"✗ {error_msg}")
        errors.append(error_msg)
    
    # If any service failed to initialize, terminate the pipeline
    if errors:
        print("\n" + "=" * 60)
        print("✗ Service initialization failed!")
        print("=" * 60)
        for error in errors:
            print(f"  - {error}")
        print("=" * 60)
        print("\nPlease check your configuration and environment variables.")
        print("The pipeline will now terminate.")
        raise RuntimeError(f"Failed to initialize {len(errors)} service(s). See errors above.")
    
    return services



