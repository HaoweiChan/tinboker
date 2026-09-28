# News Page Podcast API Implementation

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

## Summary

The NewsPage has been updated to fetch episode data from the podcast API endpoint `/api/podcast/{podcastName}/episodes/{episodeId}` when a podcast name is provided.

## Changes Made

### 1. EpisodeCard Component (`src/components/home/EpisodeCard.tsx`)

**Change:** Modified navigation to include podcast name as a query parameter.

```typescript
// Before
navigate(`/news/${episode.id}`);

// After
navigate(`/news/${episode.id}?podcast=${encodeURIComponent(episode.showName)}`);
```

**Why:** The `getEpisodeById()` function requires both `podcastName` and `episodeId`. By passing the podcast name in the URL, NewsPage can fetch the episode data directly.

### 2. NewsPage Component (`src/pages/NewsPage.tsx`)

#### Added Imports
- `useSearchParams` from `react-router-dom` - to read query parameters
- `getEpisodeById` from `@/services` - to fetch episode data from podcast API
- `Episode as ApiEpisode` type from `@/services/api`

#### Added State
- `apiEpisode: ApiEpisode | null` - stores the fetched episode data from API

#### Added Logic

1. **Extract Podcast Name from URL:**
   ```typescript
   const podcastName = searchParams.get('podcast');
   ```

2. **Fetch Episode Data from Podcast API:**
   ```typescript
   useEffect(() => {
     if (!id || !podcastName) return;

     const fetchEpisodeData = async () => {
       try {
         const episode = await fetchWithFallback(
           () => getEpisodeById(podcastName, id),
           null,
           `getEpisodeById(${podcastName}, ${id})`
         );
         setApiEpisode(episode);
       } catch (error) {
         console.error('Failed to fetch episode data:', error);
         setApiEpisode(null);
       }
     };

     fetchEpisodeData();
   }, [id, podcastName]);
   ```

3. **Updated Article Construction:**
   - Priority order:
     1. **API Episode** (from `/api/podcast/{podcastName}/episodes/{episodeId}`) - **NEW**
     2. Static Interactive Models
     3. Mock Episodes (fallback)

4. **Updated Ticker Enrichment:**
   - Now extracts tickers from `apiEpisode.related_tickers` when API episode data is available

## API Endpoint Used

**Endpoint:** `GET /api/podcast/{podcastName}/episodes/{episodeId}`

**Function:** `getEpisodeById(podcastName: string, episodeId: string)`

**Location:** `src/services/api/index.ts` (lines 659-664)

**Example:**
- Podcast Name: `"Gooaye 股癌"`
- Episode ID: `"episode-123"`
- URL: `/api/podcast/Gooaye%20%E8%82%A1%E7%99%8C/episodes/episode-123`

## Data Flow

### Before (Old Flow)
```
EpisodeCard → /news/{episodeId} → NewsPage
                                      ↓
                            getInteractiveModels() ❌
                                      ↓
                            Static/Mock Data
```

### After (New Flow)
```
EpisodeCard → /news/{episodeId}?podcast={podcastName} → NewsPage
                                                              ↓
                                                    getEpisodeById() ✅
                                                              ↓
                                                    API Episode Data
```

## Episode Data Structure

The API episode includes:
- `id`: Episode ID
- `podcast_name`: Podcast name
- `episode_title`: Episode title
- `episode_number`: Episode number
- `transcript`: Full transcript
- `summary_content`: Summary content (markdown)
- `summary_image`: Summary image URL
- `related_tickers`: Array of ticker symbols
- `tags`: Array of tags
- `created_time`: Timestamp
- `number_click`: Click count
- `num_likes`: Like count
- `raw_mp3`: MP3 URL (optional)

## Backward Compatibility

The implementation maintains backward compatibility:
- If no `podcast` query parameter is provided, NewsPage falls back to:
  1. Interactive Models API
  2. Static Interactive Models
  3. Mock Episodes

This ensures existing links and non-episode content continue to work.

## Testing

To test the implementation:

1. **Navigate from Podcaster Page:**
   - Go to `/podcaster/Gooaye%20股癌`
   - Click on an episode
   - Should navigate to `/news/{episodeId}?podcast=Gooaye%20股癌`
   - NewsPage should fetch and display episode data from API

2. **Check Network Tab:**
   - Should see request to: `GET /api/podcast/{podcastName}/episodes/{episodeId}`
   - Response should contain episode data

3. **Verify Content:**
   - Episode title should display
   - Summary content should render
   - Related tickers should be shown
   - Podcast name should be displayed as source

## Notes

- The podcast name is URL-encoded when passed in the query parameter
- The `getEpisodeById()` function handles URL encoding internally
- Error handling uses `fetchWithFallback()` which provides graceful degradation
- Ticker enrichment still works for API episodes using `related_tickers` field

