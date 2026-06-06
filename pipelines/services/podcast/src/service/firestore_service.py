"""
Generic Firestore service for data access
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

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
    
    def __init__(self):
        """Initialize Firestore service"""
        if not firebase_admin:
            raise ImportError(
                "firebase-admin is required for Firestore functionality. "
                "Install it with: pip install firebase-admin"
            )
        self._initialize_firebase()
        self.db = self._get_firestore_client()
    
    def _initialize_firebase(self) -> None:
        """
        Initialize Firebase Admin SDK with credentials from environment variables.
        Uses singleton pattern - only initializes once.
        
        Raises:
            ValueError: If required credentials are missing
            Exception: If initialization fails
        """
        if FirestoreService._initialized:
            return
        
        # Check if Firebase app is already initialized
        try:
            firebase_admin.get_app()
            FirestoreService._initialized = True
            return
        except ValueError:
            # App not initialized, proceed with initialization
            pass
        
        # Get credentials from environment
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
        
        if not credentials_path and not credentials_json:
            raise ValueError(
                "GCP_CREDENTIALS_PATH or GCP_CREDENTIALS_JSON is required. "
                "Set one of them in your .env file."
            )
        
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
        
        # Initialize Firebase Admin SDK
        try:
            firebase_admin.initialize_app(cred)
            FirestoreService._initialized = True
        except Exception as e:
            raise Exception(f"Failed to initialize Firebase Admin SDK: {e}") from e
    
    def _get_firestore_client(self) -> Any:
        """
        Get Firestore client, optionally with custom database ID.
        
        Returns:
            firestore.Client: Firestore client instance
            
        Note:
            The database must already exist in Google Cloud Console.
        """
        if FirestoreService._db is not None:
            return FirestoreService._db
        
        database_id = os.getenv("FIRESTORE_DATABASE_ID")
        
        if database_id:
            # Use custom database ID
            FirestoreService._db = firestore.client(database_id=database_id)
        else:
            # Use default database
            FirestoreService._db = firestore.client()
        
        return FirestoreService._db
    
    def get_document(self, collection: str, doc_id: str) -> Optional[Dict]:
        """
        Get a single document by ID.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            
        Returns:
            Document data as dictionary, or None if not found
        """
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
    
    def set_document(self, collection: str, doc_id: str, data: Dict, merge: bool = False) -> bool:
        """
        Create or update a document.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            data: Document data
            merge: If True, merge with existing document; if False, overwrite
            
        Returns:
            True if successful
        """
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
        """
        Query a collection with filters, ordering, and limit.
        
        Args:
            collection: Collection name
            filters: List of (field, operator, value) tuples, e.g., [("podcast_name", "==", "name")]
            order_by: Field name to order by
            direction: "ASCENDING" or "DESCENDING"
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
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
        """
        Get all documents from a collection.
        
        Args:
            collection: Collection name
            
        Returns:
            List of document dictionaries
        """
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
        """
        Delete a document.
        
        Args:
            collection: Collection name
            doc_id: Document ID
            
        Returns:
            True if successful
        """
        try:
            doc_ref = self.db.collection(collection).document(doc_id)
            doc_ref.delete()
            return True
        except Exception as e:
            raise Exception(f"Failed to delete document from Firestore: {e}") from e
    
    def get_subcollection_documents(
        self,
        collection: str,
        parent_doc_id: str,
        subcollection: str,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Get documents from a subcollection.
        
        Structure: {collection}/{parent_doc_id}/{subcollection}/{doc_id}
        
        Args:
            collection: Parent collection name (e.g., "tickers" or "tags")
            parent_doc_id: Parent document ID (e.g., ticker symbol or tag name)
            subcollection: Subcollection name (e.g., "episodes")
            order_by: Field name to order by
            direction: "ASCENDING" or "DESCENDING"
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
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
        """
        Get all parent document IDs from a collection.
        Useful for getting all tickers or tags.
        
        Args:
            collection: Collection name (e.g., "tickers" or "tags")
            
        Returns:
            List of parent document IDs
        """
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
        """
        Count documents in a subcollection.
        
        Args:
            collection: Parent collection name
            parent_doc_id: Parent document ID
            subcollection: Subcollection name
            
        Returns:
            Number of documents in subcollection
        """
        try:
            parent_doc_ref = self.db.collection(collection).document(parent_doc_id)
            subcollection_ref = parent_doc_ref.collection(subcollection)
            
            # Count by getting all and counting (Firestore doesn't have count() in Python SDK)
            count = 0
            for _ in subcollection_ref.stream():
                count += 1
            return count
        except Exception as e:
            raise Exception(f"Failed to count subcollection documents: {e}") from e

