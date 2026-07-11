import os
import logging
from typing import Any, Dict, Tuple
from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource
try:
    from google.cloud import secretmanager
    from google.api_core import exceptions
except ImportError:
    secretmanager = None
    exceptions = None


logger = logging.getLogger(__name__)

class GCPSecretManagerSource(PydanticBaseSettingsSource):
    """
    Custom Pydantic settings source that loads secrets from Google Cloud Secret Manager.
    
    It checks if GCP_PROJECT_ID is set. If so, it attempts to fetch secrets
    matching the field names (case-insensitive) from Secret Manager.
    """
    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        # This method is required by abstract base class but we implement 
        # the full dictionary loading in __call__ for efficiency
        return None, field_name, False

    def __call__(self) -> Dict[str, Any]:
        project_id = os.getenv("GCP_PROJECT_ID")

        
        # If no project ID is configured, skip Secret Manager
        if not project_id:
            logger.debug("GCP_PROJECT_ID not set, skipping Secret Manager loading")
            return {}

        if not secretmanager:
            logger.warning("google-cloud-secret-manager is not installed, skipping GCP Secret Manager loading")
            return {}

        try:
            client = secretmanager.SecretManagerServiceClient()
            secrets = {}
            
            # Iterate through all fields defined in the Settings model
            for field_name, field in self.settings_cls.model_fields.items():
                # We only want to fetch secrets for fields that might be secrets
                # You can filter by extra attributes or just define a convention.
                # Here we'll try to fetch for any field that is None in env/defaults
                # effectively using GSM as a fallback or primary source depending on priority.
                
                # Construct the secret ID from the field name (e.g., finmind_api_key -> FINMIND_API_KEY)
                secret_id = field_name.upper()
                name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
                
                try:
                    response = client.access_secret_version(request={"name": name})
                    payload = response.payload.data.decode("UTF-8")
                    secrets[field_name] = payload
                    logger.info(f"Loaded secret {secret_id} from GCP Secret Manager")
                except exceptions.NotFound:
                    # Secret not found, just skip
                    continue
                except exceptions.PermissionDenied:
                    logger.warning(f"Permission denied for secret {secret_id}")
                    continue
                except Exception as e:
                    logger.debug(f"Could not load secret {secret_id}: {e}")
                    continue
            
            return secrets
            
        except Exception as e:
            logger.error(f"Failed to initialize GCP Secret Manager client: {e}")
            return {}
