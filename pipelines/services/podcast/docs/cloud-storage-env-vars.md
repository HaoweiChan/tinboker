# Google Cloud Storage (GCS) Environment Variables

This document lists the required environment variables for uploading podcasts and transcripts to Google Cloud Storage, with detailed instructions on where to get each value.

## Required Environment Variables

Add these to your `.env` file:

```bash
# Google Cloud Storage Configuration
GCS_BUCKET_NAME=your-bucket-name
GCS_PROJECT_ID=your-project-id
GCS_CREDENTIALS_PATH=/path/to/service-account-key.json
# OR use JSON string directly (alternative to file path):
# GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key":"..."}

# Optional: Custom path prefix in bucket (default: empty)
GCS_BASE_PATH=podcasts

# Optional: Region (default: us-central1)
GCS_REGION=us-central1
```

---

## Detailed Instructions: Where to Get Each Value

### 1. `GCS_PROJECT_ID`
**Description**: Your Google Cloud Platform project ID.

**Where to get it**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. If you don't have a project yet:
   - Click the project dropdown at the top
   - Click "New Project"
   - Enter a project name (e.g., "podcast-storage")
   - Click "Create"
3. Your Project ID is displayed in the project dropdown at the top of the page
   - It's usually in the format: `your-project-name-123456`
   - Note: Project ID is different from Project Name (Project ID cannot be changed after creation)

**Example**: `GCS_PROJECT_ID=podcast-storage-123456`

---

### 2. `GCS_BUCKET_NAME`
**Description**: The name of your Google Cloud Storage bucket where files will be uploaded.

**Where to get it**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **Cloud Storage** → **Buckets** (or search "Cloud Storage" in the top search bar)
3. If you don't have a bucket yet:
   - Click "Create Bucket"
   - Enter a bucket name (must be globally unique across all GCS buckets)
     - Use lowercase letters, numbers, and hyphens only
     - Example: `my-podcast-storage` or `podcast-downloads-2024`
   - Choose a location type (Region, Multi-region, or Dual-region)
   - Choose a storage class (Standard is fine for most use cases)
   - Click "Create"
4. Your bucket name is displayed in the bucket list

**Example**: `GCS_BUCKET_NAME=my-podcast-storage`

**Note**: Bucket names must be globally unique. If your desired name is taken, try adding numbers or your project ID.

---

### 3. `GCS_CREDENTIALS_PATH`
**Description**: The file path to your service account JSON key file. This file contains authentication credentials that allow the application to access your GCS bucket.

**Where to get it**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **IAM & Admin** → **Service Accounts**
   - Or search "Service Accounts" in the top search bar
3. Click "Create Service Account"
4. Fill in the details:
   - **Service account name**: e.g., "podcast-uploader"
   - **Service account ID**: Auto-generated (you can change it)
   - **Description**: Optional (e.g., "Service account for podcast uploads")
   - Click "Create and Continue"
5. Grant roles:
   - Click "Select a role" dropdown
   - Search for and select: **Storage Object Admin** (or **Storage Admin** for full access)
   - Click "Continue"
6. Skip optional steps and click "Done"
7. Create a key:
   - Click on the newly created service account
   - Go to the "Keys" tab
   - Click "Add Key" → "Create new key"
   - Select **JSON** format
   - Click "Create"
   - A JSON file will be downloaded to your computer
8. Save the file in a secure location (e.g., `/home/lewis/.gcs-keys/podcast-uploader-key.json`)
9. Set `GCS_CREDENTIALS_PATH` to the full path of this file

**Example**: `GCS_CREDENTIALS_PATH=/home/lewis/.gcs-keys/podcast-uploader-key.json`

**Security Note**: 
- Never commit this JSON file to version control
- Keep it secure and don't share it
- The file contains sensitive credentials

---

### 4. `GCS_CREDENTIALS_JSON` (Alternative to `GCS_CREDENTIALS_PATH`)
**Description**: Instead of using a file path, you can provide the service account JSON content directly as a string. This is useful for containerized deployments.

**Where to get it**:
1. Follow steps 1-7 from `GCS_CREDENTIALS_PATH` above to download the JSON key file
2. Open the downloaded JSON file in a text editor
3. Copy the entire JSON content (it should start with `{"type":"service_account",...}`)
4. Paste it as a single-line string in your `.env` file (you may need to escape quotes)

**Example**: 
```bash
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"my-project","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",...}
```

**Note**: Use either `GCS_CREDENTIALS_PATH` OR `GCS_CREDENTIALS_JSON`, not both.

---

### 5. `GCS_BASE_PATH` (Optional)
**Description**: A custom path prefix/folder name within your bucket where files will be stored. If not set, files will be uploaded to the root of the bucket.

**Where to get it**:
- This is something you decide yourself - it's just a folder name
- Examples: `podcasts`, `downloads`, `episodes`, `2024-podcasts`, etc.
- You can organize by year: `podcasts/2024`
- Leave empty or omit this variable to upload to bucket root

**Example**: `GCS_BASE_PATH=podcasts`

**Note**: This is optional. If omitted, files will be uploaded directly to the bucket root.

---

### 6. `GCS_REGION` (Optional)
**Description**: The Google Cloud region where your bucket is located. This helps optimize API calls.

**Where to get it**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **Cloud Storage** → **Buckets**
3. Click on your bucket name
4. Look at the "Location" field - it shows the region
5. Common regions:
   - `us-central1` (Iowa, USA)
   - `us-east1` (South Carolina, USA)
   - `us-west1` (Oregon, USA)
   - `europe-west1` (Belgium)
   - `asia-east1` (Taiwan)
   - `asia-southeast1` (Singapore)
   - Or multi-region: `US`, `EU`, `ASIA`

**Example**: `GCS_REGION=us-central1`

**Note**: This is optional. If omitted, defaults to `us-central1`. It should match your bucket's location for best performance.

---

## Complete Example .env File

Here's a complete example `.env` file with all GCS variables:

```bash
# Speech-to-Text Services
DEEPGRAM_API_KEY=your-deepgram-api-key
ASSEMBLYAI_API_KEY=your-assemblyai-api-key

# Google Cloud Storage Configuration
GCS_BUCKET_NAME=my-podcast-storage-bucket
GCS_PROJECT_ID=podcast-storage-123456
GCS_CREDENTIALS_PATH=/home/lewis/.gcs-keys/podcast-uploader-key.json
GCS_BASE_PATH=podcasts
GCS_REGION=us-central1
```

---

## Quick Setup Checklist

- [ ] Created a Google Cloud Project (or selected existing one)
- [ ] Enabled Cloud Storage API
- [ ] Created a GCS bucket
- [ ] Created a service account
- [ ] Granted "Storage Object Admin" role to service account
- [ ] Downloaded service account JSON key file
- [ ] Added all required variables to `.env` file
- [ ] Tested the connection (after implementing upload function)

---

## Security Notes

- **Never commit your `.env` file** to version control
- **Never commit the service account JSON key file** to version control
- Add both to `.gitignore`:
  ```
  .env
  *.json
  .gcs-keys/
  ```
- Keep your service account keys secure and don't share them
- If a key is compromised, delete it immediately and create a new one

---

## Troubleshooting

**"Permission denied" errors**:
- Make sure the service account has "Storage Object Admin" or "Storage Admin" role
- Verify the bucket name is correct
- Check that the credentials file path is correct

**"Bucket not found" errors**:
- Verify the bucket name is spelled correctly
- Make sure the bucket exists in the specified project
- Check that you're using the correct project ID

**"Invalid credentials" errors**:
- Verify the JSON key file is valid and not corrupted
- Make sure the file path is correct and the file exists
- Try regenerating the service account key
