# infrastructure Specification

## Purpose
Define the production infrastructure for TinBoker, including VPS hosting, web server, containerization, caching layers, CDN configuration, and deployment pipelines.
## Requirements
### Requirement: VPS Hosting
The system SHALL run on a Netcup VPS located in Germany.

#### Scenario: Server Environment
- **GIVEN** the Netcup RS 1000 G11 VPS running Debian 13
- **WHEN** the server is provisioned
- **THEN** it SHALL have Docker, UFW, Fail2Ban, and Caddy installed
- **AND** a deploy user with sudo access SHALL be configured

#### Scenario: Firewall Configuration
- **GIVEN** UFW is enabled
- **WHEN** traffic reaches the server
- **THEN** only SSH (22), HTTP (80), and HTTPS (443) ports SHALL be open

### Requirement: Caddy Web Server
Caddy SHALL handle all HTTP/HTTPS traffic with automatic SSL via Let's Encrypt.

#### Scenario: Static File Serving
- **GIVEN** a request to `tinboker.com` or `dev.tinboker.com`
- **WHEN** the request path is `/` or `/assets/*`
- **THEN** Caddy SHALL serve static files from `/var/www/html` (prod) or `/var/www/html-dev` (dev)

#### Scenario: API Reverse Proxy
- **GIVEN** a request to `api.tinboker.com`
- **WHEN** the request arrives
- **THEN** Caddy SHALL reverse proxy to the local backend on port 8000

#### Scenario: Multi-Environment APIs
- **GIVEN** the Caddy configuration
- **THEN** it SHALL support multiple environment subdomains:
  - `api.tinboker.com` → port 8000 (production)
  - `dev-api.tinboker.com` → port 8001 (development)
  - `staging-api.tinboker.com` → port 8002 (staging)

### Requirement: Backend Containerization
The backend SHALL run as Docker containers via Docker Compose.

#### Scenario: Docker Compose Stack
- **GIVEN** the `docker-compose.yml` configuration
- **WHEN** `docker compose up` is run
- **THEN** it SHALL start the FastAPI backend on port 8000
- **AND** Redis cache on port 6379

#### Scenario: Redis Configuration
- **GIVEN** Redis is running
- **THEN** it SHALL be configured with:
  - Maximum memory: 2GB
  - Eviction policy: `allkeys-lru`
  - Healthcheck via `redis-cli ping`

### Requirement: Data Layer
The system SHALL use a hybrid data storage approach.

#### Scenario: Firestore for Application Data
- **GIVEN** the named Firestore database `graphfolio-db`
- **WHEN** the backend queries podcast/episode data
- **THEN** it SHALL connect to GCP Firestore using service account credentials

#### Scenario: SQLite for Local Data
- **GIVEN** the VPS environment
- **WHEN** the backend needs local structured data
- **THEN** it SHALL use SQLite stored on the VPS

#### Scenario: PostgreSQL for Translations
- **GIVEN** the GCP Cloud SQL PostgreSQL instance
- **WHEN** the backend queries stock translations
- **THEN** it SHALL connect to Cloud SQL using environment variables and Secret Manager

### Requirement: Two-Tier Caching
The system SHALL implement a two-tier caching architecture for optimal performance.

#### Scenario: Cloudflare Edge Cache (Tier 1)
- **GIVEN** a GET request to `/api/*` endpoints
- **WHEN** the response includes `Cache-Control: public, s-maxage=3600`
- **THEN** Cloudflare SHALL cache the response at 300+ global edge locations
- **AND** subsequent requests from the same region SHALL be served from edge cache

#### Scenario: Redis Origin Cache (Tier 2)
- **GIVEN** a cache miss at Cloudflare edge
- **WHEN** the request reaches the backend
- **THEN** the backend SHALL check Redis before querying the database
- **AND** cache the response in Redis for subsequent requests

#### Scenario: Cache Invalidation
- **GIVEN** content is updated
- **WHEN** cache invalidation is triggered
- **THEN** both Redis and Cloudflare caches SHALL be purged

### Requirement: Cloudflare CDN Configuration
Cloudflare SHALL provide DNS, SSL termination, and edge caching.

#### Scenario: DNS Configuration
- **GIVEN** the Cloudflare DNS zone for `tinboker.com`
- **THEN** the following records SHALL be configured:
  - A record: `api` → VPS IP (proxied)
  - A record: `dev` → VPS IP (proxied)
  - A record: `dev-api` → VPS IP (proxied)
  - CNAME: `@` (root) → `tinboker-platform.pages.dev` (proxied)

#### Scenario: SSL Mode
- **GIVEN** Cloudflare SSL/TLS settings
- **WHEN** configured
- **THEN** encryption mode SHALL be set to "Full" (Caddy provides origin certificate)

#### Scenario: Cache Rules
- **GIVEN** the Cloudflare cache rule configuration
- **WHEN** a GET request matches `/api/*`
- **THEN** it SHALL use origin cache-control headers for edge caching

### Requirement: CI/CD and Previews
The system SHALL support PR preview deployments via Cloudflare Pages.

#### Scenario: PR Preview Deployment
- **GIVEN** a pull request is opened on the WebUI repository
- **WHEN** Cloudflare Pages detects the PR
- **THEN** it SHALL build and deploy a preview at `pr-{N}.tinboker-platform.pages.dev`

#### Scenario: Production Frontend via Pages
- **GIVEN** the main branch is updated
- **WHEN** Cloudflare Pages builds the frontend
- **THEN** it SHALL be served at `tinboker.com` via the CNAME record

### Requirement: Secret Management
The system SHALL store sensitive credentials in Google Secret Manager.

#### Scenario: Secret Retrieval
- **GIVEN** the application has `GCP_PROJECT_ID` configured
- **AND** a service account with `roles/secretmanager.secretAccessor`
- **WHEN** the application starts
- **THEN** it SHALL retrieve secrets including:
  - `POSTGRES_PASSWORD`
  - `ADMIN_PASSWORD`
  - `ADMIN_JWT_SECRET`
  - `CLOUDFLARE_API_TOKEN`

#### Scenario: Local Development Fallback
- **GIVEN** the application runs in development mode
- **AND** no GCP credentials are available
- **WHEN** secrets are needed
- **THEN** it SHALL fall back to local `.env` file with a warning log

### Requirement: Deploy Script
A deployment script SHALL automate the release process.

#### Scenario: Full Deployment
- **GIVEN** the `scripts/deploy.sh` script
- **WHEN** `./scripts/deploy.sh all` is executed
- **THEN** it SHALL:
  - Build the frontend with correct `VITE_API_BASE_URL`
  - Sync frontend files to VPS `/var/www/html`
  - Sync backend code to VPS `/app`
  - Rebuild and restart Docker containers

#### Scenario: Environment-Specific Deploy
- **GIVEN** the deploy script with `--env` flag
- **WHEN** `./scripts/deploy.sh all --env dev` is executed
- **THEN** it SHALL deploy to the development environment paths

### Requirement: VPS Multi-Environment Deployment

The VPS deployment SHALL support running production, staging, and development environments simultaneously without service interference.

#### Scenario: Starting All Environments

**Given** the VPS has Docker and the app_default network configured  
**When** the operator runs `docker compose -f docker-compose.multi.yml up -d`  
**Then** three backend containers MUST start:
  - `tinboker-backend-prod` on port 8000
  - `tinboker-backend-dev` on port 8001
  - `tinboker-backend-staging` on port 8002

#### Scenario: Restarting Single Environment

**Given** all three environments are running  
**When** the operator runs `docker compose -f docker-compose.multi.yml restart backend-prod`  
**Then** only the production container SHALL restart  
**And** dev and staging containers MUST remain running

#### Scenario: Updating Single Environment Image

**Given** all three environments are running  
**When** a new image is pushed and deployment runs for production only  
**Then** only `backend-prod` SHALL pull the new image and restart  
**And** dev and staging containers MUST remain on their current images

---

### Requirement: Health Check Auto-Recovery

The health check workflow SHALL be able to restart individual unhealthy services.

#### Scenario: Production Unhealthy, Others Healthy

**Given** production returns non-200 health check  
**And** staging and dev return 200  
**When** the health check workflow runs  
**Then** only `backend-prod` SHALL be restarted  
**And** staging and dev containers MUST NOT be affected

---

### Requirement: Shared Service Management

Shared services (redis, netdata) SHALL be managed centrally and MUST NOT be duplicated.

#### Scenario: Single Redis Instance

**Given** the multi-environment compose file is used  
**When** containers are started  
**Then** exactly one redis container SHALL run (`tinboker-redis`)  
**And** all three backend services MUST connect to the same redis instance

