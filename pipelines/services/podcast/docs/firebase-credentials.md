# Google Cloud Firestore and Storage Credentials

This document explains how to set up credentials for uploading podcasts, transcripts, summaries, and images to **Google Cloud Firestore** (NoSQL database) and optionally **Google Cloud Storage** directly through Google Cloud Platform (GCP), with detailed instructions on where to get each value.

**Important**: 
- **Firestore is required** - This is where all podcast episode data (transcripts, summaries, SVG content, metadata) is stored
- **Cloud Storage is optional** - Files can be uploaded to Cloud Storage for URL access, but the actual content is always stored in Firestore
- If you only want to use Firestore, you can skip the Cloud Storage setup steps

## Required Environment Variables

Add these to your `.env` file:

```bash
# Google Cloud Firestore Configuration (REQUIRED)
GCP_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR use JSON string directly (alternative to file path):
# GCP_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Firestore Database ID (OPTIONAL - only needed if using a non-default database)
# If not specified, uses the default database "(default)"
# FIRESTORE_DATABASE_ID=your-database-id

# Google Cloud Storage Configuration (OPTIONAL - only if you want to upload files to Storage)
# GCS_BUCKET_NAME=your-gcs-bucket-name
```

**Note**: 
- **GCP_CREDENTIALS_PATH** or **GCP_CREDENTIALS_JSON** is **required** for Firestore access
- **FIRESTORE_DATABASE_ID** is **optional** - only needed if you're using a non-default database. If not specified, the code automatically uses the default database `(default)`
- **GCS_BUCKET_NAME** is **optional** - only needed if you want to upload files to Cloud Storage for URL access
- The application stores all content (transcripts, summaries, SVG) directly in Firestore regardless of Storage setup

---
### 2. `GCS_BUCKET_NAME` (OPTIONAL)
**Description**: Your Google Cloud Storage (GCS) bucket name. This is **optional** - files can be uploaded here for URL access, but all content is also stored directly in Firestore. If you only want to use Firestore, you can skip this.

**Where to get it**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. If you don't have a project yet:
   - Click the project dropdown at the top
   - Click "New Project"
   - Enter a project name (e.g., "podcast-storage")
   - Click "Create"
   - Wait for project creation to complete
3. Once in your project:
   - Navigate to **Cloud Storage** → **Buckets** (or search "Cloud Storage" in the top search bar)
   - If you don't have a bucket yet:
     - Click "Create Bucket"
     - Enter a bucket name (must be globally unique across all GCS buckets)
       - Use lowercase letters, numbers, and hyphens only
       - Example: `my-podcast-storage` or `podcast-downloads-2024`
     - Choose a location type (Region, Multi-region, or Dual-region)
     - Choose a storage class (Standard is fine for most use cases)
     - Click "Create"
4. Your bucket name is displayed in the bucket list
   - Example: `my-podcast-storage` or `podcast-storage-123456`

**Example**: `GCS_BUCKET_NAME=my-podcast-storage`

**Note**: Bucket names must be globally unique. If your desired name is taken, try adding numbers or your project ID.

---

### 3. `GCP_CREDENTIALS_JSON` (Alternative to `GCP_CREDENTIALS_PATH`)
**Description**: Instead of using a file path, you can provide the service account JSON content directly as a string. This is useful for containerized deployments or CI/CD pipelines.

**Where to get it**:
1. Follow steps 1-8 from `GCP_CREDENTIALS_PATH` above to download the JSON key file
2. Open the downloaded JSON file in a text editor
3. Copy the entire JSON content (it should start with `{"type":"service_account",...}`)
4. Paste it as a single-line string in your `.env` file
   - You may need to escape quotes or use single quotes around the JSON string
   - Alternatively, you can keep it as a multi-line string in some environments

**Example**: 
```bash
GCP_CREDENTIALS_JSON='{"type":"service_account","project_id":"podcast-storage-123456","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}'
```

**Note**: Use either `GCP_CREDENTIALS_PATH` OR `GCP_CREDENTIALS_JSON`, not both. The file path method is recommended for local development.

---

## Firestore Database Setup

### Database ID Configuration

**Important**: You typically **do NOT need to specify a database ID**. Here's why:

- **Default Database**: Firestore automatically creates a default database with ID `(default)` when you create a Firestore database
- **Automatic Connection**: The Firebase Admin SDK automatically connects to the default database if no database ID is specified
- **Multiple Databases**: You only need to specify `FIRESTORE_DATABASE_ID` if:
  - You've created multiple databases in your project
  - You want to use a non-default database (e.g., for testing/staging environments)

**If you're using the default database** (most common case):
- ✅ Just set `GCP_CREDENTIALS_PATH` - that's all you need!
- ✅ No need to set `FIRESTORE_DATABASE_ID`
- ✅ The code will automatically connect to `(default)` database

**If you need a custom database ID** (e.g., `graphfolio-db`):
1. **IMPORTANT**: Create the database FIRST in Google Cloud Console:
   - Go to: https://console.cloud.google.com/firestore/databases
   - Click "Create Database"
   - Choose "Native mode" (recommended)
   - Enter your database ID (e.g., `graphfolio-db`)
   - Select location and click "Create"
   - **Note**: Databases cannot be created programmatically - they must be created manually
2. Set `FIRESTORE_DATABASE_ID=your-database-id` in your `.env` file
   - Example: `FIRESTORE_DATABASE_ID=graphfolio-db`
3. Database ID requirements:
   - 4-63 characters
   - Lowercase letters, numbers, and hyphens only
   - Must start with a letter
   - Must end with a letter or number

### Data Structure

The application uses Google Cloud Firestore (NoSQL database) to store podcast episode data. 

**Important**: Each episode is stored as a **separate document** to avoid Firestore's 1MB document size limit. This allows unlimited episodes per podcast.

The structure is:

```
episodes/                           (collection)
  └── {podcast_name}_ep{episode_number}  (document ID - uses episode_number for stable matching)
      └── Fields:
          - podcast_name: string
          - episode_title: string
          - episode_number: integer (for deduplication)
          - episode_id: string (same as document ID)
          - transcript: string (full transcript text)
          - summary_content: string (markdown summary)
          - summary_image: string (SVG content)
          - related_tickers: array of strings
          - created_time: timestamp
          - number_click: integer
          - num_likes: integer
          - raw_mp3: string (empty, not stored in Firestore)
```
      ├── podcast_name: string
      ├── episode_title: string
      ├── transcript: string (full transcript text)
      ├── summary_content: string (markdown summary)
      ├── summary_image: string (SVG content)
      ├── related_tickers: array
      ├── created_time: timestamp
      ├── number_click: number
      └── num_likes: number
```

Where:
- `episodes` is the collection name
- Document ID format: `{podcast_name}_ep{episode_number}` (when episode_number available) or `{podcast_name}_{hash16}` (fallback)
- Each document contains one complete episode with all its data
- Episodes can be queried by `podcast_name` field
- The `episode_number` field enables efficient deduplication in cron service mode

**Why this structure?**
- Firestore has a **1MB limit per document**
- Podcast transcripts are large (~60KB each)
- Storing all episodes in one document would quickly exceed the limit
- Storing each episode separately allows unlimited scalability

**Firestore Security Rules** (for production):
You may want to set up Firestore security rules. For initial testing, you can use:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /podcasts/{document=**} {
      allow read, write: if request.auth != null;
      // Or for public read (adjust based on your needs):
      // allow read: if true;
      // allow write: if request.auth != null;
    }
  }
}
```

To set rules:
1. Go to **Firestore** in Google Cloud Console
2. Click on the **Rules** tab
3. Edit the rules as needed
4. Click "Publish"

**Note**: When using the Firebase Admin SDK (which this application uses), security rules are bypassed because the Admin SDK uses service account credentials with elevated privileges. Rules apply to client-side access.

---

## Google Cloud Storage Setup

**Storage Access Control**:
Since the application uses the Firebase Admin SDK with service account credentials, it has full access to your Cloud Storage bucket. For public access to files, you can:

1. Make individual files public:
   - Go to **Cloud Storage** → **Buckets** in Google Cloud Console
   - Click on your bucket
   - Navigate to the file
   - Click on the file
   - Click "Edit permissions"
   - Add "allUsers" with "Reader" role

2. Or use signed URLs (recommended):
   - The application generates signed URLs for uploaded files
   - These URLs have expiration dates and don't require public access

**Note**: The application uses service account credentials, which bypass IAM-based access controls. Service account permissions are controlled through IAM roles (Storage Object Admin) rather than bucket-level permissions.

---

## Complete Example .env File

Here's a complete example `.env` file with all Google Cloud variables:

```bash
# Speech-to-Text Services
DEEPGRAM_API_KEY=your-deepgram-api-key
ASSEMBLYAI_API_KEY=your-assemblyai-api-key

# Google Cloud Firestore and Storage Configuration
GCS_BUCKET_NAME=my-podcast-storage
GCP_CREDENTIALS_PATH=/home/lewis/.gcp-keys/podcast-service-account.json

# Alternative: Use JSON string instead of file path
# GCP_CREDENTIALS_JSON={"type":"service_account","project_id":"podcast-storage-123456",...}
```


## Testing Your Setup

To test your Google Cloud configuration:

1. Make sure all environment variables are set in your `.env` file
2. Run the pipeline with only the upload step:
   ```bash
   python main.py --skip-download --skip-transcribe --skip-summarize
   ```
3. Check the Google Cloud Console:
   - **Cloud Storage** → **Buckets**: Should see uploaded files (transcripts, summaries, SVG images)
   - **Firestore**: Should see a document at `podcasts/podcast` with fields like `{podcast_name: [episode_data_array]}`

---

## Additional Resources

- [Google Cloud Console](https://console.cloud.google.com/)
- [Firebase Admin SDK Documentation](https://firebase.google.com/docs/admin/setup) (works with GCP projects)
- [Cloud Firestore Documentation](https://cloud.google.com/firestore/docs)
- [Google Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Service Accounts Documentation](https://cloud.google.com/iam/docs/service-accounts)

