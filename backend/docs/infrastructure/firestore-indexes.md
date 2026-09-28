# Analysis: Why `tickers` and `tags` Collections Appear Empty

> **Historical design record.** This page reflects an earlier implementation or proposal.
> Do not use its setup, deployment, or migration commands for the current service.
> Start with the [backend README](../../README.md) and [infra runbook](../../../docs/infra-runbook.md).

## Summary

The collections **ARE being populated**, but they use a **subcollection structure**:
- `tickers/{ticker}/episodes/{episode_id}` ✅ (Data exists!)
- `tags/{tag}/episodes/{episode_id}` ✅ (Data exists!)

The parent documents in `tickers` and `tags` collections are **empty containers** (no fields), but they contain subcollections with episode references.

## Actual Data Structure

### Confirmed Structure:
```
tickers/
  └── orcl/                    (parent document - empty container)
      └── episodes/             (subcollection)
          └── {episode_id}/      (episode reference document)
              ├── episode_id: "87a8b530_727783ce128de8a9"
              ├── created_time: DatetimeWithNanoseconds
              ├── podcast_name: "財經一路發"
              ├── episode_title: "那指再探關鍵位置  V轉機會？ 2025.12.18"
              └── episode_number: None
```

## Code Analysis

### The Code DOES Work:
1. ✅ `_update_index_collections()` is called in `upload_podcast_data()`
2. ✅ `_update_ticker_collection()` creates documents in subcollections
3. ✅ `_update_tag_collection()` creates documents in subcollections
4. ✅ Data is being stored correctly (confirmed by test)

### Potential Issues:

#### 1. **`created_time` Type Handling**
The code stores `episode.created_time` directly:
```python
episode_data = {
    'created_time': episode.created_time,  # Could be datetime or string
    ...
}
```

**Issue**: When `episode.created_time` is:
- ✅ `datetime` object → Works (Firestore accepts it)
- ✅ `DatetimeWithNanoseconds` → Works (from Firestore reads)
- ⚠️ **String (ISO format)** → Might fail silently or cause issues

**From `to_firestore_dict()`**:
```python
'created_time': self.created_time.isoformat() if isinstance(self.created_time, datetime) else self.created_time
```
This converts datetime to ISO string for the main episode document, but the subcollection code uses `episode.created_time` directly.

#### 2. **Silent Failures**
The code has try/except blocks that only print warnings:
```python
except Exception as e:
    print(f"  ⚠ Warning: Failed to update ticker collection for {ticker}: {e}")
```

If there's an error (e.g., type mismatch), it fails silently and continues.

#### 3. **Empty Arrays Handling**
The code handles empty arrays:
```python
for ticker in episode.related_tickers or []:
    self._update_ticker_collection(ticker, episode_id, episode, add=True)
```

If `related_tickers` is `None` or empty, nothing happens (which is correct).

## Why Collections Appear Empty

When querying `tickers` or `tags` collections directly:
```python
tickers_collection = db.collection("tickers")
docs = list(tickers_collection.stream())  # Gets parent documents
```

This returns **parent documents** which are:
- Empty containers (no fields)
- But contain subcollections

To see the actual data, you need to:
```python
ticker_ref = db.collection("tickers").document("orcl").collection("episodes")
docs = list(ticker_ref.stream())  # Gets episode references
```

## Recommendations

### 1. **Fix `created_time` Type Handling**
Ensure `created_time` is always a datetime object when storing to subcollections:

```python
def _update_ticker_collection(...):
    # Convert created_time to datetime if it's a string
    if isinstance(episode.created_time, str):
        from datetime import datetime
        created_time = datetime.fromisoformat(episode.created_time.replace('Z', '+00:00'))
    elif hasattr(episode.created_time, 'isoformat'):
        created_time = episode.created_time  # Already datetime
    else:
        created_time = datetime.now()  # Fallback
    
    episode_data = {
        'created_time': created_time,  # Always datetime object
        ...
    }
```

### 2. **Better Error Handling**
Instead of silent failures, log errors properly:
```python
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to update ticker collection for {ticker}: {e}", exc_info=True)
    # Don't fail silently - re-raise or handle appropriately
```

### 3. **Add Validation**
Validate that tickers/tags are being updated:
```python
def _update_index_collections(...):
    ticker_count = len(episode.related_tickers or [])
    tag_count = len(episode.tags or [])
    print(f"  📊 Updating {ticker_count} tickers and {tag_count} tags...")
    
    # Update logic...
    
    print(f"  ✓ Updated index collections")
```

### 4. **Query Methods Work Correctly**
The `get_episodes_by_ticker()` and `get_episodes_by_tag()` methods should work correctly since they query subcollections:
```python
def get_episodes_by_ticker(self, ticker: str, ...):
    ticker_doc_ref = tickers_collection.document(ticker.lower())
    episodes_subcollection = ticker_doc_ref.collection("episodes")
    # This correctly queries the subcollection ✅
```

## Conclusion

**The collections ARE being populated correctly!** The structure uses subcollections, not direct documents. The parent documents are empty containers, which is why they appear empty when queried directly.

The main potential issue is `created_time` type handling - ensure it's always a datetime object when storing to subcollections.

