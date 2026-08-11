import os
import logging
from typing import Any, Dict, Iterable, Optional, Set, Tuple
from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource
try:
    from google.cloud import secretmanager
    from google.api_core import exceptions
except ImportError:
    secretmanager = None
    exceptions = None


logger = logging.getLogger(__name__)


# ── P6 (GCP decommission) ─────────────────────────────────────────────────────
# The full set of settings fields that were ever stored in Google Secret Manager.
# They now come from the environment: compose/backend/.env on the VPS (docker
# compose injects it) or plain env vars locally. GSM is retained ONLY as a
# fallback for values the operator has not migrated yet.
#
# To retire the fallback: confirm no "source=gsm" lines remain in the backend
# logs, then delete this list, GCPSecretManagerSource, its entry in
# Settings.settings_customise_sources, and the google-cloud-secret-manager dep.
#
# NOTE: this list is deliberately over-inclusive — a name that is not in GSM just
# 404s harmlessly, whereas a missing name would silently lose a live secret.
_GSM_FIELDS: Tuple[str, ...] = (
    # Market data
    "finmind_api_key",
    "finmind_api_keys",
    "finmind_hourly_cap",
    "massive_api_key",
    "massive_api_keys",
    # Content tier
    "podcast_api_key",
    # Auth
    "google_client_id",
    "google_client_secret",
    "jwt_secret_key",
    "admin_emails",
    "dev_bypass_token",
    # Service tokens
    "tinboker_write_token",
    "tinboker_article_token",
    "tinboker_social_token",
    "internal_api_key",
    # Social publishing
    "threads_access_token",
    "threads_user_id",
    "facebook_page_id",
    "facebook_page_access_token",
    # 方格子 — the token expires every 7 days and is replaced by hand; the ids are public.
    "vocus_id_token",
    "vocus_user_id",
    "vocus_salon_id",
    # GCP / GCS article store — still needed, see docs/firestore-contract.md §11.8
    "google_application_credentials",
    "gsc_site_url",
    # Cloudflare
    "cloudflare_api_token",
    "cloudflare_zone_tag",
    # Datastores
    "postgres_url",
    "postgres_password",
    "redis_url",
    "redis_password",
)


def _gsm_client():  # pragma: no cover - exercised only on the legacy fallback path
    """Construct the Secret Manager client.

    Split out so tests can patch it and assert that a fully-populated environment
    never reaches Secret Manager.
    """
    return secretmanager.SecretManagerServiceClient()


class GCPSecretManagerSource(PydanticBaseSettingsSource):
    """Pydantic settings source: legacy Google Secret Manager fallback.

    Lowest priority — env vars and .env win (see
    ``Settings.settings_customise_sources``). Anything those already supplied is
    skipped here, so once every secret lives in the environment no Secret Manager
    client is ever constructed and no network call is made.
    """

    def __init__(
        self,
        settings_cls,
        resolved: Optional[Iterable[str]] = None,
    ) -> None:
        super().__init__(settings_cls)
        # Field names already served by a higher-priority source.
        self._resolved: Set[str] = {name.lower() for name in (resolved or ())}

    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> Tuple[Any, str, bool]:
        # Required by the abstract base class; the real work is in __call__ so a
        # single pass can decide whether Secret Manager is needed at all.
        return None, field_name, False

    def __call__(self) -> Dict[str, Any]:
        missing = [f for f in _GSM_FIELDS if f not in self._resolved]
        if not missing:
            logger.info("config: all secrets served from the environment; skipping GSM")
            return {}

        project_id = os.getenv("GCP_PROJECT_ID")
        if not project_id:
            logger.debug("GCP_PROJECT_ID not set, skipping Secret Manager loading")
            return {}

        if not secretmanager:
            logger.warning("google-cloud-secret-manager is not installed, skipping GCP Secret Manager loading")
            return {}

        try:
            client = _gsm_client()
        except Exception as e:
            logger.error(f"Failed to initialize GCP Secret Manager client: {e}")
            return {}

        secrets: Dict[str, Any] = {}
        for field_name in missing:
            secret_id = field_name.upper()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            try:
                response = client.access_secret_version(request={"name": name})
                secrets[field_name] = response.payload.data.decode("UTF-8")
                logger.warning(
                    f"config: {secret_id} source=gsm (migrate it into compose/backend/.env)"
                )
            except exceptions.NotFound:
                continue
            except exceptions.PermissionDenied:
                logger.warning(f"Permission denied for secret {secret_id}")
                continue
            except Exception as e:
                logger.debug(f"Could not load secret {secret_id}: {e}")
                continue

        return secrets
