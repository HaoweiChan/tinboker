"""
Generic Firestore service for data access
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    firebase_admin = None
    credentials = None
    firestore = None


class FirestoreService:
    """
    Generic service for Firestore operations.
    Can be used for any collection/document structure.
    """
    
    _initialized = False
    _db: Optional[Any] = None
    _disabled = False  # Circuit breaker flag
    
    def __init__(self):
        """Initialize Firestore service"""
        if not firebase_admin:
            # If library is missing, disable immediately
            logger.warning("firebase-admin not installed. Firestore disabled.")
            FirestoreService._disabled = True
            return

        try:
            self._initialize_firebase()
            self.db = self._get_firestore_client()
        except Exception as e:
            logger.warning(f"Firestore initialization failed: {e}. Firestore will be disabled.")
            FirestoreService._disabled = True
            self.db = None
    
    def _initialize_firebase(self) -> None:
        """
        Initialize Firebase Admin SDK with credentials from environment variables.
        Uses singleton pattern - only initializes once.
        """
        if FirestoreService._initialized:
            return
            
        if FirestoreService._disabled:
            return
        
        # Check if Firebase app is already initialized
        try:
            firebase_admin.get_app()
            FirestoreService._initialized = True
            return
        except ValueError:
            # App not initialized, proceed with initialization
            pass
        
        # Get credentials from settings (supports .env and GSM)
        
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
        
        if not credentials_path and not credentials_json:
            # Fallback to default google auth if available (e.g. cloud run identity)
            # We want to allow this for ADC support
            logger.info("No explicit credentials found, attempting to use Application Default Credentials")
            
        # Initialize credentials
        cred = None
        if credentials_path:
            # Use credentials from file path
            cred_path = Path(credentials_path).expanduser().resolve()
            if not cred_path.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {cred_path}"
                )
            cred = credentials.Certificate(str(cred_path))
        elif credentials_json:
            # Use credentials from JSON string
            try:
                if isinstance(credentials_json, str):
                    creds_dict = json.loads(credentials_json)
                else:
                    creds_dict = credentials_json
                cred = credentials.Certificate(creds_dict)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in GCP_CREDENTIALS_JSON: {e}"
                ) from e
        else:
            # Use Application Default Credentials (ADC)
            try:
                import google.auth
                from firebase_admin import credentials as fb_credentials
                
                google_creds, project = google.auth.default()
                cred = fb_credentials.ApplicationDefault()
                logger.info(f"Using Application Default Credentials for project: {project}")
            except Exception as e:
                # If ADC fails, we must disable
                logger.warning(f"Failed to get Application Default Credentials: {e}")
                raise
        
        # Initialize Firebase Admin SDK
        try:
            firebase_admin.initialize_app(cred)
            FirestoreService._initialized = True
        except Exception as e:
            raise Exception(f"Failed to initialize Firebase Admin SDK: {e}") from e
    
    def _get_firestore_client(self) -> Any:
        """
        Get Firestore client, optionally with custom database ID.
        """
        if FirestoreService._disabled:
            return None
            
        if FirestoreService._db is not None:
            return FirestoreService._db
        
        database_id = os.getenv("FIRESTORE_DATABASE_ID")
        
        if database_id:
            try:
                from google.cloud import firestore as google_firestore
                
                # Get credentials from the initialized Firebase app
                app = firebase_admin.get_app()
                creds = app.credential.get_credential()
                project = app.project_id
                
                logger.info(f"Initializing Firestore with named database: {database_id} (project: {project})")
                FirestoreService._db = google_firestore.Client(
                    project=project, 
                    credentials=creds, 
                    database=database_id
                )
            except Exception as e:
                logger.error(f"Failed to initialize named Firestore database '{database_id}': {e}")
                raise
        else:
            # Use default database
            FirestoreService._db = firestore.client()
        
        return FirestoreService._db
    
    def get_document(self, collection: str, doc_id: str) -> Optional[Dict]:
        """Get a single document by ID."""
        if self._disabled or not self.db:
            return None

        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id  # Include document ID
                return data
            else:
                return None
        except Exception as e:
            raise Exception(f"Failed to get document from Firestore: {e}") from e
    
    def get_documents_batch(self, collection: str, doc_ids: List[str]) -> List[Dict]:
        """Batch-read multiple documents by ID using Firestore get_all()."""
        if self._disabled or not self.db or not doc_ids:
            return []
        try:
            refs = [self.db.collection(collection).document(did) for did in doc_ids]
            results = []
            for doc in self.db.get_all(refs):
                if doc.exists:
                    data = doc.to_dict()
                    data['id'] = doc.id
                    results.append(data)
            return results
        except Exception as e:
            raise Exception(f"Failed to batch-get documents from Firestore: {e}") from e

    def set_document(self, collection: str, doc_id: str, data: Dict, merge: bool = False) -> bool:
        """Create or update a document."""
        if self._disabled or not self.db:
            return False

        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            if merge:
                doc_ref.set(data, merge=True)
            else:
                doc_ref.set(data)
            return True
        except Exception as e:
            raise Exception(f"Failed to set document in Firestore: {e}") from e
    
    def query_collection(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None
    ) -> List[Dict]:
        """Query a collection with filters, ordering, and limit."""
        if self._disabled or not self.db:
            return []

        try:
            query = self.db.collection(collection)
            
            # Apply filters
            if filters:
                for field, operator, value in filters:
                    if operator == "==":
                        query = query.where(field, "==", value)
                    elif operator == ">":
                        query = query.where(field, ">", value)
                    elif operator == "<":
                        query = query.where(field, "<", value)
                    elif operator == ">=":
                        query = query.where(field, ">=", value)
                    elif operator == "<=":
                        query = query.where(field, "<=", value)
                    elif operator == "!=":
                        query = query.where(field, "!=", value)
                    elif operator == "in":
                        query = query.where(field, "in", value)
                    elif operator == "array-contains":
                        query = query.where(field, "array_contains", value)

            # Apply ordering
            if order_by:
                direction_enum = firestore.Query.DESCENDING if direction == "DESCENDING" else firestore.Query.ASCENDING
                query = query.order_by(order_by, direction=direction_enum)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            results = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id  # Include document ID
                results.append(data)
            
            return results
        except Exception as e:
            raise Exception(f"Failed to query collection in Firestore: {e}") from e
    
    def get_all_documents(self, collection: str) -> List[Dict]:
        """Get all documents from a collection."""
        if self._disabled or not self.db:
            return []

        try:
            results = []
            for doc in self.db.collection(collection).stream():
                data = doc.to_dict()
                data['id'] = doc.id
                results.append(data)
            return results
        except Exception as e:
            raise Exception(f"Failed to get all documents from Firestore: {e}") from e
    
    def delete_document(self, collection: str, doc_id: str) -> bool:
        """Delete a document."""
        if self._disabled or not self.db:
            return False

        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            return True
        except Exception as e:
            raise Exception(f"Failed to delete document from Firestore: {e}") from e
    
    def query_collection_group(
        self,
        collection_id: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict]:
        """
        Query a collection group: matches every subcollection (and root collection)
        with the given collection_id, regardless of parent path.

        Used by ticker_insights reads where docs live at
        `ticker_insights/{episode_id}/tickers/{ticker}` — the subcollection name
        is "tickers", same as the existing root `tickers/*` inverted index.
        Callers MUST filter results by supported `schema_version` values to
        disambiguate from the inverted-index docs.
        """
        if self._disabled or not self.db:
            return []

        try:
            query = self.db.collection_group(collection_id)

            if filters:
                for field, operator, value in filters:
                    query = query.where(field, operator, value)

            if order_by:
                direction_enum = (
                    firestore.Query.DESCENDING
                    if direction == "DESCENDING"
                    else firestore.Query.ASCENDING
                )
                query = query.order_by(order_by, direction=direction_enum)

            if limit:
                query = query.limit(limit)

            results: List[Dict] = []
            for doc in query.stream():
                data = doc.to_dict()
                data["id"] = doc.id
                # Capture the parent doc id (e.g. episode_id for
                # ticker_insights/{episode_id}/tickers/{ticker}) so callers can
                # reconstruct paths without a second round-trip.
                try:
                    parent_doc_ref = doc.reference.parent.parent
                    if parent_doc_ref is not None:
                        data["_parent_id"] = parent_doc_ref.id
                except Exception:
                    pass
                results.append(data)
            return results
        except Exception as e:
            raise Exception(
                f"Failed to query collection group in Firestore: {e}"
            ) from e

    def get_subcollection_documents(
        self,
        collection: str,
        parent_doc_id: str,
        subcollection: str,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None
    ) -> List[Dict]:
        """Get documents from a subcollection."""
        if self._disabled or not self.db:
            return []

        try:
            parent_doc_ref = self.db.collection(collection).document(parent_doc_id)
            subcollection_ref = parent_doc_ref.collection(subcollection)
            
            query = subcollection_ref
            
            # Apply ordering
            if order_by:
                direction_enum = firestore.Query.DESCENDING if direction == "DESCENDING" else firestore.Query.ASCENDING
                query = query.order_by(order_by, direction=direction_enum)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Execute query
            results = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id  # Include document ID
                results.append(data)
            
            return results
        except Exception as e:
            raise Exception(f"Failed to get subcollection documents from Firestore: {e}") from e
    
    def get_all_parent_documents(self, collection: str) -> List[str]:
        """Get all parent document IDs from a collection."""
        if self._disabled or not self.db:
            return []

        try:
            parent_ids = []
            for doc in self.db.collection(collection).stream():
                parent_ids.append(doc.id)
            return parent_ids
        except Exception as e:
            raise Exception(f"Failed to get parent documents from Firestore: {e}") from e
    
    def count_subcollection_documents(
        self,
        collection: str,
        parent_doc_id: str,
        subcollection: str
    ) -> int:
        """Count documents in a subcollection."""
        if self._disabled or not self.db:
            return 0

        try:
            parent_doc_ref = self.db.collection(collection).document(parent_doc_id)
            subcollection_ref = parent_doc_ref.collection(subcollection)
            
            # Count by getting all and counting
            count = 0
            for _ in subcollection_ref.stream():
                count += 1
            return count
        except Exception as e:
            raise Exception(f"Failed to count subcollection documents: {e}") from e
