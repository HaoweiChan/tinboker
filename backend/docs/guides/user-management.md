# User Management and Google Login Features Guide

**Date:** 2025-12-22  
**Project:** TinBoker (Backend + Frontend)  
**Purpose:** Guide for managing user data and extending Google login functionality

---

## Table of Contents

1. [Checking User Login Information in Database](#checking-user-login-information-in-database)
2. [Extending Google Login Features](#extending-google-login-features)
3. [User Preferences and Data Storage](#user-preferences-and-data-storage)
4. [Implementation Examples](#implementation-examples)
5. [API Endpoints for User Features](#api-endpoints-for-user-features)

---

## Checking User Login Information in Database

### Method 1: Using SQLite Command Line

**Connect to the database:**
```bash
cd tinboker-platform/backend
sqlite3 data/tinboker.db
```

**View all users:**
```sql
SELECT * FROM users;
```

**View specific user by email:**
```sql
SELECT * FROM users WHERE email = 'user@example.com';
```

**View user by Google ID:**
```sql
SELECT * FROM users WHERE google_id = '123456789012345678901';
```

**View users with formatted output:**
```sql
.mode column
.headers on
SELECT id, google_id, email, name, email_verified, created_at, updated_at FROM users;
```

**Count total users:**
```sql
SELECT COUNT(*) as total_users FROM users;
```

**View recent users:**
```sql
SELECT * FROM users ORDER BY created_at DESC LIMIT 10;
```

**Exit SQLite:**
```sql
.quit
```

### Method 2: Using Python Script

Create a script to query users:

```python
# scripts/view_users.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.user_db import get_user_by_email, get_user_by_google_id
from src.database.db import get_connection

def view_all_users():
    """View all users in the database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, google_id, email, name, avatar, email_verified, created_at, updated_at
        FROM users
        ORDER BY created_at DESC
    """)
    
    users = cursor.fetchall()
    
    print(f"\nTotal users: {len(users)}\n")
    print(f"{'ID':<36} {'Email':<30} {'Name':<20} {'Verified':<8} {'Created At'}")
    print("-" * 120)
    
    for user in users:
        print(f"{user['id']:<36} {user['email']:<30} {user['name']:<20} {str(user['email_verified']):<8} {user['created_at']}")
    
    conn.close()

def view_user_by_email(email: str):
    """View specific user by email"""
    user = get_user_by_email(email)
    if user:
        print(f"\nUser found:")
        print(f"  ID: {user.id}")
        print(f"  Google ID: {user.google_id}")
        print(f"  Email: {user.email}")
        print(f"  Name: {user.name}")
        print(f"  Avatar: {user.avatar}")
        print(f"  Email Verified: {user.email_verified}")
        print(f"  Created At: {user.created_at}")
        print(f"  Updated At: {user.updated_at}")
    else:
        print(f"User with email {email} not found")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        view_user_by_email(sys.argv[1])
    else:
        view_all_users()
```

**Usage:**
```bash
# View all users
python scripts/view_users.py

# View specific user
python scripts/view_users.py user@example.com
```

### Method 3: Using FastAPI Endpoint

You can also query users via the API:

```bash
# Get current user (requires authentication)
curl -X GET http://localhost:3000/api/auth/me \
  -H "Authorization: Bearer your-jwt-token"
```

### Method 4: Database Schema Reference

**Users Table Structure:**
```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,                    -- UUID
    google_id TEXT UNIQUE NOT NULL,         -- Google UID (sub claim)
    email TEXT UNIQUE NOT NULL,             -- User email
    name TEXT NOT NULL,                     -- Display name
    avatar TEXT,                            -- Profile picture URL
    email_verified BOOLEAN DEFAULT FALSE,   -- Email verification status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:**
- `idx_users_google_id` on `google_id`
- `idx_users_email` on `email`

---

## Extending Google Login Features

Now that users can log in with Google, you can implement various user-specific features. Here are common use cases:

### 1. User Preferences

Store user preferences like:
- Theme preference (dark/light mode)
- Language settings
- Notification preferences
- Default timeframes for charts

### 2. User-Generated Content

Allow users to:
- Like/favorite posts or episodes
- Bookmark articles
- Save watchlists
- Create custom portfolios

### 3. Social Features

Implement:
- Follow/unfollow podcasters
- Share content
- Comment on articles
- User profiles

### 4. Personalization

- Personalized recommendations
- Reading history
- Search history
- Custom alerts/notifications

---

## User Preferences and Data Storage

### Database Schema Design

Here are recommended database tables for extending user features:

#### 1. User Preferences Table

```sql
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    theme TEXT DEFAULT 'dark',              -- 'dark' or 'light'
    language TEXT DEFAULT 'zh_TW',          -- Language preference
    timezone TEXT DEFAULT 'Asia/Taipei',    -- User timezone
    notifications_enabled BOOLEAN DEFAULT TRUE,
    email_notifications BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### 2. User Likes/Favorites Table

```sql
CREATE TABLE IF NOT EXISTS user_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,             -- 'post', 'episode', 'stock', etc.
    content_id TEXT NOT NULL,                -- ID of the liked content
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, content_type, content_id)
);

CREATE INDEX IF NOT EXISTS idx_user_likes_user_id ON user_likes(user_id);
CREATE INDEX IF NOT EXISTS idx_user_likes_content ON user_likes(content_type, content_id);
```

#### 3. User Watchlists Table

```sql
CREATE TABLE IF NOT EXISTS user_watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    ticker TEXT NOT NULL,                   -- Stock ticker symbol
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (ticker) REFERENCES stocks(ticker) ON DELETE CASCADE,
    UNIQUE(user_id, ticker)
);

CREATE INDEX IF NOT EXISTS idx_user_watchlists_user_id ON user_watchlists(user_id);
```

#### 4. User Follows Table (for Podcasters)

```sql
CREATE TABLE IF NOT EXISTS user_follows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    podcaster_name TEXT NOT NULL,            -- Podcast/podcaster name
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, podcaster_name)
);

CREATE INDEX IF NOT EXISTS idx_user_follows_user_id ON user_follows(user_id);
```

#### 5. User Bookmarks Table

```sql
CREATE TABLE IF NOT EXISTS user_bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,             -- 'news', 'episode', etc.
    content_id TEXT NOT NULL,
    notes TEXT,                              -- Optional user notes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE(user_id, content_type, content_id)
);

CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user_id ON user_bookmarks(user_id);
```

#### 6. User Reading History Table

```sql
CREATE TABLE IF NOT EXISTS user_reading_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_id TEXT NOT NULL,
    last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    progress INTEGER DEFAULT 0,              -- Reading progress (0-100)
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_reading_history_user_id ON user_reading_history(user_id, last_read_at DESC);
```

---

## Implementation Examples

### Example 1: User Preferences API

**Create `src/database/user_preferences_db.py`:**

```python
"""
User preferences database operations
"""
from typing import Optional
from datetime import datetime
from src.database.db import get_connection


def init_user_preferences_table():
    """Initialize user preferences table"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            theme TEXT DEFAULT 'dark',
            language TEXT DEFAULT 'zh_TW',
            timezone TEXT DEFAULT 'Asia/Taipei',
            notifications_enabled BOOLEAN DEFAULT TRUE,
            email_notifications BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()


def get_user_preferences(user_id: str) -> Optional[dict]:
    """Get user preferences"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT theme, language, timezone, notifications_enabled, email_notifications
        FROM user_preferences
        WHERE user_id = ?
    """, (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'theme': row['theme'],
            'language': row['language'],
            'timezone': row['timezone'],
            'notifications_enabled': bool(row['notifications_enabled']),
            'email_notifications': bool(row['email_notifications']),
        }
    return None


def update_user_preferences(user_id: str, **preferences) -> dict:
    """Update user preferences"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get existing preferences or create default
    existing = get_user_preferences(user_id)
    if not existing:
        # Create default preferences
        cursor.execute("""
            INSERT INTO user_preferences (user_id, theme, language, timezone, notifications_enabled, email_notifications)
            VALUES (?, 'dark', 'zh_TW', 'Asia/Taipei', TRUE, FALSE)
        """, (user_id,))
        existing = get_user_preferences(user_id)
    
    # Update only provided preferences
    updates = []
    params = []
    
    if 'theme' in preferences:
        updates.append("theme = ?")
        params.append(preferences['theme'])
    
    if 'language' in preferences:
        updates.append("language = ?")
        params.append(preferences['language'])
    
    if 'timezone' in preferences:
        updates.append("timezone = ?")
        params.append(preferences['timezone'])
    
    if 'notifications_enabled' in preferences:
        updates.append("notifications_enabled = ?")
        params.append(preferences['notifications_enabled'])
    
    if 'email_notifications' in preferences:
        updates.append("email_notifications = ?")
        params.append(preferences['email_notifications'])
    
    if updates:
        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(user_id)
        
        cursor.execute(f"""
            UPDATE user_preferences
            SET {', '.join(updates)}
            WHERE user_id = ?
        """, params)
        
        conn.commit()
    
    conn.close()
    return get_user_preferences(user_id)
```

**Create API endpoint in `src/routers/user.py`:**

```python
"""
User-specific routes
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from src.utils.dependencies import get_current_user
from src.models.user import UserResponse
from src.database.user_preferences_db import get_user_preferences, update_user_preferences, init_user_preferences_table

router = APIRouter(prefix="/api/user", tags=["user"])


@router.on_event("startup")
async def startup_event():
    """Initialize user preferences table on startup"""
    init_user_preferences_table()


@router.get("/preferences")
async def get_preferences(user: UserResponse = Depends(get_current_user)):
    """Get current user's preferences"""
    preferences = get_user_preferences(user.id)
    if not preferences:
        # Return defaults if not set
        return {
            'theme': 'dark',
            'language': 'zh_TW',
            'timezone': 'Asia/Taipei',
            'notifications_enabled': True,
            'email_notifications': False,
        }
    return preferences


@router.put("/preferences")
async def update_preferences(
    preferences: dict,
    user: UserResponse = Depends(get_current_user)
):
    """Update current user's preferences"""
    updated = update_user_preferences(user.id, **preferences)
    return updated
```

### Example 2: User Likes/Favorites API

**Create `src/database/user_likes_db.py`:**

```python
"""
User likes/favorites database operations
"""
from typing import List, Optional
from datetime import datetime
from src.database.db import get_connection


def init_user_likes_table():
    """Initialize user likes table"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            content_type TEXT NOT NULL,
            content_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, content_type, content_id)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_likes_user_id ON user_likes(user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_likes_content ON user_likes(content_type, content_id)
    """)
    
    conn.commit()
    conn.close()


def add_like(user_id: str, content_type: str, content_id: str) -> bool:
    """Add a like (returns True if added, False if already exists)"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_likes (user_id, content_type, content_id)
            VALUES (?, ?, ?)
        """, (user_id, content_type, content_id))
        conn.commit()
        return True
    except Exception:
        # Already liked
        conn.rollback()
        return False
    finally:
        conn.close()


def remove_like(user_id: str, content_type: str, content_id: str) -> bool:
    """Remove a like"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM user_likes
        WHERE user_id = ? AND content_type = ? AND content_id = ?
    """, (user_id, content_type, content_id))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def is_liked(user_id: str, content_type: str, content_id: str) -> bool:
    """Check if user has liked a content"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 1 FROM user_likes
        WHERE user_id = ? AND content_type = ? AND content_id = ?
        LIMIT 1
    """, (user_id, content_type, content_id))
    
    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_user_likes(user_id: str, content_type: Optional[str] = None) -> List[dict]:
    """Get all likes for a user, optionally filtered by content type"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if content_type:
        cursor.execute("""
            SELECT content_type, content_id, created_at
            FROM user_likes
            WHERE user_id = ? AND content_type = ?
            ORDER BY created_at DESC
        """, (user_id, content_type))
    else:
        cursor.execute("""
            SELECT content_type, content_id, created_at
            FROM user_likes
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
    
    likes = [
        {
            'content_type': row['content_type'],
            'content_id': row['content_id'],
            'created_at': row['created_at']
        }
        for row in cursor.fetchall()
    ]
    
    conn.close()
    return likes


def get_like_count(content_type: str, content_id: str) -> int:
    """Get total like count for a content"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM user_likes
        WHERE content_type = ? AND content_id = ?
    """, (content_type, content_id))
    
    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0
```

**Add endpoints to `src/routers/user.py`:**

```python
from src.database.user_likes_db import (
    add_like, remove_like, is_liked, get_user_likes, get_like_count,
    init_user_likes_table
)

@router.on_event("startup")
async def startup_event():
    init_user_preferences_table()
    init_user_likes_table()  # Add this


@router.post("/likes/{content_type}/{content_id}")
async def toggle_like(
    content_type: str,
    content_id: str,
    user: UserResponse = Depends(get_current_user)
):
    """Like or unlike content"""
    if is_liked(user.id, content_type, content_id):
        remove_like(user.id, content_type, content_id)
        return {"liked": False, "count": get_like_count(content_type, content_id)}
    else:
        add_like(user.id, content_type, content_id)
        return {"liked": True, "count": get_like_count(content_type, content_id)}


@router.get("/likes")
async def get_my_likes(
    content_type: Optional[str] = None,
    user: UserResponse = Depends(get_current_user)
):
    """Get current user's likes"""
    return get_user_likes(user.id, content_type)


@router.get("/likes/{content_type}/{content_id}/status")
async def check_like_status(
    content_type: str,
    content_id: str,
    user: UserResponse = Depends(get_current_user)
):
    """Check if current user has liked content"""
    return {
        "liked": is_liked(user.id, content_type, content_id),
        "count": get_like_count(content_type, content_id)
    }
```

### Example 3: User Watchlist API

**Create `src/database/user_watchlist_db.py`:**

```python
"""
User watchlist database operations
"""
from typing import List
from src.database.db import get_connection


def init_user_watchlist_table():
    """Initialize user watchlist table"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            ticker TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (ticker) REFERENCES stocks(ticker) ON DELETE CASCADE,
            UNIQUE(user_id, ticker)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_watchlists_user_id ON user_watchlists(user_id)
    """)
    
    conn.commit()
    conn.close()


def add_to_watchlist(user_id: str, ticker: str) -> bool:
    """Add ticker to user's watchlist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO user_watchlists (user_id, ticker)
            VALUES (?, ?)
        """, (user_id, ticker))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def remove_from_watchlist(user_id: str, ticker: str) -> bool:
    """Remove ticker from user's watchlist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM user_watchlists
        WHERE user_id = ? AND ticker = ?
    """, (user_id, ticker))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_watchlist(user_id: str) -> List[str]:
    """Get user's watchlist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT ticker FROM user_watchlists
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    
    tickers = [row['ticker'] for row in cursor.fetchall()]
    conn.close()
    return tickers


def is_in_watchlist(user_id: str, ticker: str) -> bool:
    """Check if ticker is in user's watchlist"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 1 FROM user_watchlists
        WHERE user_id = ? AND ticker = ?
        LIMIT 1
    """, (user_id, ticker))
    
    result = cursor.fetchone() is not None
    conn.close()
    return result
```

---

## API Endpoints for User Features

### Recommended Endpoints Structure

```
GET    /api/user/preferences          - Get user preferences
PUT    /api/user/preferences          - Update user preferences

POST   /api/user/likes/{type}/{id}   - Toggle like on content
GET    /api/user/likes                - Get user's likes
GET    /api/user/likes/{type}/{id}/status - Check like status

POST   /api/user/watchlist/{ticker}   - Add to watchlist
DELETE /api/user/watchlist/{ticker}   - Remove from watchlist
GET    /api/user/watchlist            - Get user's watchlist

POST   /api/user/follow/{podcaster}   - Follow podcaster
DELETE /api/user/follow/{podcaster}   - Unfollow podcaster
GET    /api/user/follows              - Get followed podcasters

POST   /api/user/bookmarks            - Add bookmark
DELETE /api/user/bookmarks/{id}       - Remove bookmark
GET    /api/user/bookmarks            - Get user's bookmarks

GET    /api/user/history              - Get reading history
POST   /api/user/history              - Update reading progress
```

### Protected Routes

All user-specific endpoints should require authentication. Use the `get_current_user` dependency:

```python
from src.utils.dependencies import get_current_user
from src.models.user import UserResponse

@router.get("/preferences")
async def get_preferences(user: UserResponse = Depends(get_current_user)):
    # user.id, user.email, etc. are available here
    pass
```

---

## Frontend Integration

### Update Zustand Store

The frontend already has some user preferences in the store. You can extend it:

```typescript
// In src/store/useAppStore.ts
interface AppState {
  // ... existing state ...
  
  // User preferences (sync with backend)
  userPreferences: {
    theme: 'dark' | 'light';
    language: string;
    timezone: string;
    notifications_enabled: boolean;
  };
  
  // User data
  userLikes: string[];  // Array of content IDs
  userWatchlist: string[];  // Array of tickers
  userFollows: string[];  // Array of podcaster names
  
  // Actions
  setUserPreferences: (prefs: Partial<UserPreferences>) => void;
  toggleLike: (contentId: string) => void;
  toggleWatchlist: (ticker: string) => void;
  toggleFollow: (podcaster: string) => void;
}
```

### API Service for User Features

Create `src/services/api/user.ts`:

```typescript
import axios from 'axios';
import { useAppStore } from '@/store/useAppStore';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000/api';

export const userApi = {
  getPreferences: async () => {
    const token = useAppStore.getState().token;
    const response = await axios.get(`${API_BASE_URL}/user/preferences`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  },

  updatePreferences: async (preferences: any) => {
    const token = useAppStore.getState().token;
    const response = await axios.put(`${API_BASE_URL}/user/preferences`, preferences, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  },

  toggleLike: async (contentType: string, contentId: string) => {
    const token = useAppStore.getState().token;
    const response = await axios.post(
      `${API_BASE_URL}/user/likes/${contentType}/${contentId}`,
      {},
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.data;
  },

  getWatchlist: async () => {
    const token = useAppStore.getState().token;
    const response = await axios.get(`${API_BASE_URL}/user/watchlist`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.data;
  },

  addToWatchlist: async (ticker: string) => {
    const token = useAppStore.getState().token;
    await axios.post(`${API_BASE_URL}/user/watchlist/${ticker}`, {}, {
      headers: { Authorization: `Bearer ${token}` }
    });
  },

  removeFromWatchlist: async (ticker: string) => {
    const token = useAppStore.getState().token;
    await axios.delete(`${API_BASE_URL}/user/watchlist/${ticker}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
  },
};
```

---

## Database Migration

When adding new tables, update the migration script:

**Update `src/database/db.py`:**

```python
def init_db():
    # ... existing tables ...
    
    # Add user-related tables
    from src.database.user_preferences_db import init_user_preferences_table
    from src.database.user_likes_db import init_user_likes_table
    from src.database.user_watchlist_db import init_user_watchlist_table
    
    init_user_preferences_table()
    init_user_likes_table()
    init_user_watchlist_table()
```

Or create a separate migration:

```python
# src/database/migrate_user_features.py
from src.database.user_preferences_db import init_user_preferences_table
from src.database.user_likes_db import init_user_likes_table
from src.database.user_watchlist_db import init_user_watchlist_table

if __name__ == "__main__":
    init_user_preferences_table()
    init_user_likes_table()
    init_user_watchlist_table()
    print("User feature tables initialized")
```

---

## Quick Reference: Database Queries

### Check User Login Status

```sql
-- See all logged-in users (users who have accounts)
SELECT COUNT(*) FROM users;

-- See recently registered users
SELECT email, name, created_at 
FROM users 
ORDER BY created_at DESC 
LIMIT 10;

-- Check if specific email is registered
SELECT * FROM users WHERE email = 'user@example.com';
```

### Check User Activity

```sql
-- Users with most likes
SELECT u.email, COUNT(l.id) as like_count
FROM users u
LEFT JOIN user_likes l ON u.id = l.user_id
GROUP BY u.id
ORDER BY like_count DESC;

-- Users with watchlists
SELECT u.email, COUNT(w.ticker) as watchlist_count
FROM users u
LEFT JOIN user_watchlists w ON u.id = w.user_id
GROUP BY u.id
HAVING watchlist_count > 0;
```

### Clean Up Test Data

```sql
-- Delete a test user (cascades to all related data)
DELETE FROM users WHERE email = 'test@example.com';

-- Delete all test users
DELETE FROM users WHERE email LIKE '%test%';
```

---

## Best Practices

### 1. Data Privacy

- Always validate user ownership before allowing data access
- Use `get_current_user` dependency for all user-specific endpoints
- Never expose other users' data

### 2. Performance

- Add indexes on frequently queried columns
- Use pagination for large result sets
- Cache user preferences in Redis if needed

### 3. Data Consistency

- Use foreign keys with CASCADE delete
- Use transactions for multi-step operations
- Validate data before database operations

### 4. Security

- Always verify JWT tokens
- Sanitize user input
- Use parameterized queries (already done with ? placeholders)

---

## Next Steps

1. **Implement User Preferences API** - Start with preferences endpoint
2. **Add Like/Favorite Feature** - Most common user interaction
3. **Implement Watchlist** - Already partially in frontend store
4. **Add Follow Feature** - For podcasters
5. **Create User Dashboard** - Show user's activity and preferences

---

## Example: Complete User Features Implementation

See the implementation examples above for:
- `src/database/user_preferences_db.py` - Preferences management
- `src/database/user_likes_db.py` - Likes/favorites system
- `src/database/user_watchlist_db.py` - Watchlist management
- `src/routers/user.py` - User API endpoints

These can be implemented step by step as needed.

---

**Last Updated:** 2025-12-22  
**Related Documents:**
- [Google Login Implementation Guide](./google_login_implementation_guide.md)
- [Google Login Setup Guide](./google_login_setup_guide.md)

