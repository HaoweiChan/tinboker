# News Page Logic Comparison: Intended vs Current Implementation

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

## Intended Logic

1. **Podcaster Page** (`/podcaster/Gooaye%20股癌`):
   - Shows a list of podcasts (episodes)
   - Each episode has an ID (e.g., `"Gooaye%20%E8%82%A1%E7%99%8C"` or episode-specific ID)

2. **News Page** (`/news/{episodeId}`):
   - Should fetch episode data from: `GET /api/podcast/{podcastName}` or episode-specific endpoint
   - Display the content provided by that endpoint

## Current Implementation

### Podcaster Page (`/podcaster/:id`)

**Current Behavior:**
- ✅ Fetches podcast metadata: `GET /api/podcast/{podcastName}` via `getPodcastByName()`
- ✅ Fetches episodes list: `GET /api/podcast/{podcastName}/episodes` via `getPodcastEpisodes()`
- ✅ Displays episodes with their IDs

**Code Location:** `src/pages/PodcasterPage.tsx` (lines 81-93)

### News Page (`/news/:id`)

**Current Behavior:**
- ❌ **Does NOT fetch from podcast API endpoint**
- ❌ Instead calls: `GET /api/visuals/interactive-models` via `getInteractiveModels()`
- ❌ Falls back to static mock data: `INTERACTIVE_MODELS` or `MOCK_EPISODES`
- ✅ Only enriches ticker data with `getStockByTicker()` calls

**Code Location:** `src/pages/NewsPage.tsx` (lines 287-309)

**Current Flow:**
```typescript
// Current implementation in NewsPage.tsx
useEffect(() => {
  if (!id) return;
  
  const fetchModelData = async () => {
    try {
      // ❌ WRONG: Fetches ALL interactive models, then searches
      const models = await getInteractiveModels();
      const model = models.find((m: any) => m.id === id);
      // ...
    }
  };
  
  // Falls back to static data
  const staticArticle = INTERACTIVE_MODELS[id || ''] || null;
  const mockEpisode = !staticArticle ? MOCK_EPISODES.find(e => e.id === id) : null;
}, [id]);
```

## Key Differences

| Aspect | Intended Logic | Current Implementation |
|--------|---------------|----------------------|
| **API Endpoint** | `GET /api/podcast/{podcastName}` or episode endpoint | `GET /api/visuals/interactive-models` |
| **Data Source** | Podcast API (episode data) | Interactive models API + static mock data |
| **Episode Lookup** | Direct fetch by episode ID | Search through all interactive models |
| **Fallback** | API error handling | Static mock data (`MOCK_EPISODES`, `INTERACTIVE_MODELS`) |

## Available API Functions

The codebase already has the function to fetch episode data:

**Function:** `getEpisodeById(podcastName: string, episodeId: string)`
- **Location:** `src/services/api/index.ts` (lines 659-664)
- **Endpoint:** `GET /api/podcast/{podcastName}/episodes/{episodeId}`
- **Status:** ✅ Defined but **NOT USED** in NewsPage

**Alternative:** If episodes can be fetched directly by ID without podcast name:
- Would need a new endpoint: `GET /api/episodes/{episodeId}`
- Currently not available in the API

## Problem Analysis

### Issue 1: Episode ID vs Podcast Name Confusion

The user mentioned the ID as `"Gooaye%20%E8%82%A1%E7%99%8C"` which looks like a **podcast name** (URL-encoded "Gooaye 股癌"), not an **episode ID**.

**Important Finding:**
- The `Episode` interface (from API) includes both:
  - `id: string` - The episode ID
  - `podcast_name: string` - The podcast name
- So episodes have their own unique IDs, separate from podcast names

**Questions to clarify:**
1. Is the episode ID the same as the podcast name? (No - episodes have unique IDs)
2. Or does the episode ID need to be extracted from the episode data? (No - it's in the episode object)
3. Or should there be a different endpoint that accepts episode ID directly? (Would be helpful but not currently available)

### Issue 2: Missing Episode Data Fetch

The NewsPage currently:
- ❌ Does not fetch episode data from the podcast API
- ❌ Relies on interactive models or mock data
- ❌ Does not use the existing `getEpisodeById()` function
- ❌ Does not have access to `podcast_name` when only episode ID is in the URL

### Issue 3: Episode Navigation Flow

**Current Flow:**
```
EpisodeCard → navigate(`/news/${episode.id}`) → NewsPage
```

**NewsPage receives:** `episode.id` (from Episode interface)

**But NewsPage:**
- Does not know which podcast the episode belongs to
- Cannot call `getEpisodeById(podcastName, episodeId)` without the podcast name

## Required Changes

To implement the intended logic, NewsPage needs to:

1. **Option A: Fetch episode by ID directly (if endpoint exists)**
   ```typescript
   // Would need: GET /api/episodes/{episodeId}
   const episode = await getEpisodeByIdDirect(episodeId);
   ```

2. **Option B: Extract podcast name from episode ID or store it**
   - Store podcast name when navigating from EpisodeCard
   - Or include podcast name in the episode ID format
   - Then call: `getEpisodeById(podcastName, episodeId)`

3. **Option C: Use a different endpoint**
   - If `GET /api/podcast/{podcastName}` returns episode data when the name matches an episode ID
   - This seems unlikely based on API structure

## Recommended Solution

Based on the current API structure, the best approach would be:

### Solution 1: Pass Podcast Name in URL (Recommended)

1. **Modify EpisodeCard** to pass podcast name along with episode ID:
   ```typescript
   // In EpisodeCard.tsx line 21
   navigate(`/news/${episode.id}?podcast=${encodeURIComponent(episode.showName)}`);
   ```

2. **Update NewsPage** to:
   - Extract podcast name from URL query params
   - Call `getEpisodeById(podcastName, episodeId)` to fetch episode data
   - Display the episode content (transcript, summary_content, etc.)

### Solution 2: Fetch All Episodes and Find by ID (Less Efficient)

1. **Update NewsPage** to:
   - First fetch all podcasts: `getSortedPodcasts()`
   - For each podcast, fetch episodes: `getPodcastEpisodes()`
   - Find the episode with matching ID
   - Display the episode content

   **Note:** This is inefficient as it requires multiple API calls.

### Solution 3: Backend Endpoint (Requires Backend Changes)

If backend provides a direct endpoint:
   - `GET /api/episodes/{episodeId}` that doesn't require podcast name
   - This would be cleaner but requires backend changes

### Solution 4: User's Mentioned Endpoint (Needs Clarification)

The user mentioned: `GET /api/podcast/Gooaye%20%E8%82%A1%E7%99%8C`

**Possible interpretations:**
- If this endpoint returns episode data when the podcast name matches an episode ID (unlikely)
- If this is a typo and should be `/api/podcast/{podcastName}/episodes/{episodeId}`
- If there's a new endpoint structure we're not aware of

**Recommendation:** Use Solution 1 (pass podcast name in URL) as it's the cleanest with current API structure.

## Code Locations Summary

| Component | File | Current Behavior | Should Do |
|-----------|------|-----------------|------------|
| **PodcasterPage** | `src/pages/PodcasterPage.tsx` | ✅ Fetches episodes correctly | ✅ Already correct |
| **NewsPage** | `src/pages/NewsPage.tsx` | ❌ Uses wrong API | Fetch episode from podcast API |
| **EpisodeCard** | `src/components/home/EpisodeCard.tsx` | Navigates with episode.id | May need to pass podcast name |
| **API Function** | `src/services/api/index.ts` | `getEpisodeById()` exists | ✅ Use it in NewsPage |

