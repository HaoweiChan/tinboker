# Google Login Implementation Guide

**Date:** 2025-12-22  
**Project:** TinBoker (Backend + Frontend)  
**Purpose:** Complete guide for implementing Google OAuth authentication

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Google Cloud Console Setup](#google-cloud-console-setup)
4. [Backend Implementation](#backend-implementation)
5. [Frontend Implementation](#frontend-implementation)
6. [Database Schema](#database-schema)
7. [Security Considerations](#security-considerations)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)

---

## Overview

This guide provides step-by-step instructions for implementing Google OAuth login in the TinBoker application. The implementation uses:

- **Backend**: FastAPI with Firebase Admin SDK for token verification
- **Frontend**: React with `@react-oauth/google` library
- **Authentication Flow**: OAuth 2.0 with ID tokens

### Architecture Flow

```
User clicks "Login with Google"
    ↓
Frontend: Google OAuth popup
    ↓
User authenticates with Google
    ↓
Frontend: Receives ID token from Google
    ↓
Frontend: Sends ID token to Backend (/api/auth/google)
    ↓
Backend: Verifies token with Firebase Admin SDK
    ↓
Backend: Creates/updates user in database
    ↓
Backend: Returns JWT session token + user info
    ↓
Frontend: Stores token and user info in Zustand store
    ↓
User is authenticated
```

---

## Prerequisites

### Backend Dependencies

The following packages are already installed in `requirements.txt`:
- `firebase-admin>=6.0.0` ✅ (Already installed)
- `fastapi==0.104.1` ✅ (Already installed)
- `pydantic==2.5.0` ✅ (Already installed)

**Additional packages needed:**
- `python-jose[cryptography]` - For JWT token generation
- `passlib[bcrypt]` - For password hashing (if needed for future features)

### Frontend Dependencies

The following package is already installed in `package.json`:
- `@react-oauth/google@^0.12.2` ✅ (Already installed)

### Google Cloud Setup

You'll need:
1. A Google Cloud Project
2. OAuth 2.0 credentials (Client ID and Client Secret)
3. Firebase Admin SDK service account credentials (JSON file)

---

## Google Cloud Console Setup

### Step 1: Create OAuth 2.0 Credentials

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/
   - Select or create a project

2. **Enable Google+ API**
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google+ API" and enable it
   - (Note: Google+ API is deprecated but still needed for OAuth)

3. **Create OAuth 2.0 Client ID**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - If prompted, configure OAuth consent screen first:
     - User Type: External (for public apps) or Internal (for organization)
     - App name: "TinBoker"
     - User support email: Your email
     - Developer contact: Your email
     - Save and continue through scopes and test users
   
4. **Configure OAuth Client**
   - Application type: **Web application**
   - Name: "TinBoker Web Client"
   - **Authorized JavaScript origins:**
     ```
     http://localhost:5173
     http://localhost:5175
     https://your-production-domain.com
     https://*.vercel.app  (for Vercel preview deployments)
     ```
   - **Authorized redirect URIs:**
     ```
     http://localhost:5173
     http://localhost:5175
     https://your-production-domain.com
     ```
   - Click "Create"
   - **Save the Client ID** - You'll need this for the frontend

### Step 2: Create Firebase Project (for Backend Token Verification)

1. **Go to Firebase Console**
   - Visit: https://console.firebase.google.com/
   - Create a new project or select existing one
   - Enable Google Analytics (optional)

2. **Generate Service Account Key**
   - Go to Project Settings (gear icon) > "Service accounts"
   - Click "Generate new private key"
   - Download the JSON file
   - **Save this file securely** - You'll need it for backend configuration

3. **Note the Project ID**
   - The Firebase project ID is visible in the project settings
   - You'll need this for backend configuration

### Step 3: Environment Variables

**Backend (.env):**
```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id-from-oauth-credentials.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-from-oauth-credentials

# Firebase Admin SDK (for token verification)
# Option 1: Path to service account JSON file
GCP_CREDENTIALS_PATH=/path/to/service-account-key.json

# Option 2: Service account JSON as environment variable (for production)
# GCP_CREDENTIALS_JSON={"type": "service_account", "project_id": "...", ...}

# Firebase Project ID
FIREBASE_PROJECT_ID=your-firebase-project-id

# JWT Secret (for session tokens)
JWT_SECRET_KEY=your-random-secret-key-min-32-chars
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
```

**Frontend (.env or .env.local):**
```env
VITE_GOOGLE_CLIENT_ID=your-client-id-from-oauth-credentials.apps.googleusercontent.com
VITE_API_URL=http://localhost:3000/api  # Backend API URL
```

---

## Backend Implementation

### Step 1: Install Additional Dependencies

Add to `requirements.txt`:
```txt
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
```

Then install:
```bash
pip install python-jose[cryptography] passlib[bcrypt]
```

### Step 2: Update Configuration

Add to `src/config.py`:

```python
# Add to Settings class
# Google OAuth Configuration
google_client_id: Optional[str] = None
google_client_secret: Optional[str] = None

# JWT Configuration
jwt_secret_key: Optional[str] = None
jwt_algorithm: str = "HS256"
jwt_expiration_hours: int = 24

# Firebase Project ID (for token verification)
firebase_project_id: Optional[str] = None
```

### Step 3: Create Authentication Utilities

Create `src/utils/auth.py`:

```python
"""
Authentication utilities for Google OAuth and JWT tokens
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from firebase_admin import auth as firebase_auth, credentials, initialize_app
from firebase_admin.exceptions import FirebaseError
from src.config import settings

# Initialize Firebase Admin SDK
_firebase_initialized = False

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    global _firebase_initialized
    if _firebase_initialized:
        return
    
    try:
        # Try to get credentials from environment variable (JSON string)
        creds_json = os.getenv("GCP_CREDENTIALS_JSON")
        if creds_json:
            import json
            creds_dict = json.loads(creds_json)
            cred = credentials.Certificate(creds_dict)
        else:
            # Try to get credentials from file path
            creds_path = os.getenv("GCP_CREDENTIALS_PATH") or settings.gcp_credentials_path
            if creds_path:
                cred = credentials.Certificate(creds_path)
            else:
                raise ValueError("Firebase credentials not configured")
        
        initialize_app(cred, {
            'projectId': os.getenv("FIREBASE_PROJECT_ID") or settings.firebase_project_id
        })
        _firebase_initialized = True
    except Exception as e:
        print(f"Warning: Firebase Admin SDK initialization failed: {e}")
        print("Google login will not work until Firebase is configured")


def verify_google_token(id_token: str) -> Dict[str, Any]:
    """
    Verify Google ID token using Firebase Admin SDK
    
    Args:
        id_token: Google ID token from frontend
        
    Returns:
        Decoded token payload containing user information
        
    Raises:
        ValueError: If token is invalid or verification fails
    """
    if not _firebase_initialized:
        initialize_firebase()
    
    try:
        # Verify the ID token
        decoded_token = firebase_auth.verify_id_token(id_token)
        
        # Extract user information
        user_info = {
            'uid': decoded_token.get('uid'),
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'picture': decoded_token.get('picture'),
            'email_verified': decoded_token.get('email_verified', False),
        }
        
        return user_info
    except FirebaseError as e:
        raise ValueError(f"Firebase token verification failed: {str(e)}")
    except Exception as e:
        raise ValueError(f"Token verification failed: {str(e)}")


def create_jwt_token(user_id: str, email: str) -> str:
    """
    Create a JWT session token for the user
    
    Args:
        user_id: User's unique identifier
        email: User's email address
        
    Returns:
        Encoded JWT token string
    """
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    expiration = datetime.utcnow() + timedelta(hours=settings.jwt_expiration_hours)
    
    payload = {
        'sub': user_id,  # Subject (user ID)
        'email': email,
        'exp': expiration,
        'iat': datetime.utcnow(),
    }
    
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )
    
    return token


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT session token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload or None if invalid
    """
    if not settings.jwt_secret_key:
        return None
    
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
```

### Step 4: Create User Database Model

Create `src/models/user.py`:

```python
"""
User models for authentication
"""
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """Base user model"""
    email: EmailStr
    name: str
    avatar: Optional[str] = None


class UserCreate(UserBase):
    """User creation model"""
    google_id: str  # Google UID


class UserResponse(UserBase):
    """User response model"""
    id: str
    google_id: str
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Authentication response model"""
    user: UserResponse
    token: str  # JWT session token
```

### Step 5: Create User Database Operations

Create `src/database/user_db.py`:

```python
"""
User database operations
"""
from typing import Optional
from datetime import datetime
from src.database.db import get_connection
from src.models.user import UserCreate, UserResponse


def init_user_table():
    """Initialize users table"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            google_id TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            avatar TEXT,
            email_verified BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index on google_id for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id)
    """)
    
    # Create index on email for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
    """)
    
    conn.commit()


def get_user_by_google_id(google_id: str) -> Optional[UserResponse]:
    """Get user by Google ID"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, google_id, email, name, avatar, email_verified, created_at, updated_at
        FROM users
        WHERE google_id = ?
    """, (google_id,))
    
    row = cursor.fetchone()
    if row:
        return UserResponse(
            id=row['id'],
            google_id=row['google_id'],
            email=row['email'],
            name=row['name'],
            avatar=row['avatar'],
            email_verified=bool(row['email_verified']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
    return None


def get_user_by_email(email: str) -> Optional[UserResponse]:
    """Get user by email"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, google_id, email, name, avatar, email_verified, created_at, updated_at
        FROM users
        WHERE email = ?
    """, (email,))
    
    row = cursor.fetchone()
    if row:
        return UserResponse(
            id=row['id'],
            google_id=row['google_id'],
            email=row['email'],
            name=row['name'],
            avatar=row['avatar'],
            email_verified=bool(row['email_verified']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )
    return None


def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user"""
    import uuid
    
    conn = get_connection()
    cursor = conn.cursor()
    
    user_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    cursor.execute("""
        INSERT INTO users (id, google_id, email, name, avatar, email_verified, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        user_data.google_id,
        user_data.email,
        user_data.name,
        user_data.avatar,
        False,  # email_verified will be set from Google token
        now,
        now
    ))
    
    conn.commit()
    
    return get_user_by_google_id(user_data.google_id)


def update_user(google_id: str, name: Optional[str] = None, avatar: Optional[str] = None, email_verified: Optional[bool] = None) -> Optional[UserResponse]:
    """Update user information"""
    conn = get_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    
    if avatar is not None:
        updates.append("avatar = ?")
        params.append(avatar)
    
    if email_verified is not None:
        updates.append("email_verified = ?")
        params.append(email_verified)
    
    if not updates:
        return get_user_by_google_id(google_id)
    
    updates.append("updated_at = ?")
    params.append(datetime.utcnow().isoformat())
    params.append(google_id)
    
    cursor.execute(f"""
        UPDATE users
        SET {', '.join(updates)}
        WHERE google_id = ?
    """, params)
    
    conn.commit()
    
    return get_user_by_google_id(google_id)


def get_or_create_user(google_id: str, email: str, name: str, avatar: Optional[str] = None, email_verified: bool = False) -> UserResponse:
    """Get existing user or create new one"""
    user = get_user_by_google_id(google_id)
    
    if user:
        # Update user info if changed
        updated_user = update_user(
            google_id,
            name=name if name != user.name else None,
            avatar=avatar if avatar != user.avatar else None,
            email_verified=email_verified if email_verified != user.email_verified else None
        )
        return updated_user or user
    
    # Create new user
    from src.models.user import UserCreate
    user_data = UserCreate(
        google_id=google_id,
        email=email,
        name=name,
        avatar=avatar
    )
    return create_user(user_data)
```

### Step 6: Create Authentication Router

Create `src/routers/auth.py`:

```python
"""
Authentication routes for Google OAuth
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from src.models.user import AuthResponse
from src.database.user_db import get_or_create_user, init_user_table
from src.utils.auth import verify_google_token, create_jwt_token, verify_jwt_token

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.on_event("startup")
async def startup_event():
    """Initialize user table on startup"""
    init_user_table()


@router.post("/google", response_model=AuthResponse)
async def google_login(request: dict):
    """
    Authenticate user with Google ID token
    
    Request body:
    {
        "idToken": "google-id-token-string"
    }
    
    Returns:
    {
        "user": {
            "id": "user-uuid",
            "google_id": "google-uid",
            "email": "user@example.com",
            "name": "User Name",
            "avatar": "https://...",
            "email_verified": true,
            "created_at": "2025-12-22T...",
            "updated_at": "2025-12-22T..."
        },
        "token": "jwt-session-token"
    }
    """
    id_token = request.get("idToken")
    
    if not id_token:
        raise HTTPException(
            status_code=400,
            detail="idToken is required"
        )
    
    try:
        # Verify Google token
        google_user = verify_google_token(id_token)
        
        # Get or create user in database
        user = get_or_create_user(
            google_id=google_user['uid'],
            email=google_user['email'],
            name=google_user.get('name', 'User'),
            avatar=google_user.get('picture'),
            email_verified=google_user.get('email_verified', False)
        )
        
        # Create JWT session token
        jwt_token = create_jwt_token(user.id, user.email)
        
        return AuthResponse(
            user=user,
            token=jwt_token
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.get("/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Get current authenticated user from JWT token
    
    Headers:
        Authorization: Bearer <jwt-token>
    
    Returns:
        User information
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required"
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )
    
    # Verify JWT token
    payload = verify_jwt_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # Get user from database
    from src.database.user_db import get_user_by_email
    user = get_user_by_email(payload['email'])
    
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    return user


@router.post("/logout")
async def logout():
    """
    Logout endpoint (client-side token removal)
    
    Note: Since we're using stateless JWT tokens, logout is handled
    client-side by removing the token. This endpoint exists for
    consistency and future token blacklisting if needed.
    """
    return {"message": "Logged out successfully"}
```

### Step 7: Register Router in Main App

Update `src/main.py`:

```python
# Add import
from src.routers.auth import router as auth_router

# Add to router registration (after line 89)
app.include_router(auth_router)
```

### Step 8: Update Database Migration

Update `src/database/migrate.py` to include user table initialization:

```python
# Add to migration script
from src.database.user_db import init_user_table

# In the main migration function
init_user_table()
```

### Step 9: Create Authentication Dependency (Optional)

Create `src/utils/dependencies.py` for protected routes:

```python
"""
FastAPI dependencies for authentication
"""
from fastapi import Depends, HTTPException, Header
from typing import Optional
from src.utils.auth import verify_jwt_token
from src.database.user_db import get_user_by_email
from src.models.user import UserResponse


async def get_current_user(authorization: Optional[str] = Header(None)) -> UserResponse:
    """
    Dependency to get current authenticated user
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: UserResponse = Depends(get_current_user)):
            return {"user_id": user.id}
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required"
        )
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format"
        )
    
    payload = verify_jwt_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    user = get_user_by_email(payload['email'])
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    return user
```

---

## Frontend Implementation

### Step 1: Update Environment Variables

Create or update `.env.local` in `tinboker-platform/frontend`:

```env
VITE_GOOGLE_CLIENT_ID=your-client-id-from-oauth-credentials.apps.googleusercontent.com
VITE_API_URL=http://localhost:3000/api
```

### Step 2: Update Google OAuth Provider Setup

Update `src/main.tsx` or `src/App.tsx`:

```typescript
import { GoogleOAuthProvider } from '@react-oauth/google';

// Get client ID from environment
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

function App() {
  return (
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      {/* Your existing app components */}
    </GoogleOAuthProvider>
  );
}
```

### Step 3: Update LoginButton Component

Update `src/components/auth/LoginButton.tsx`:

```typescript
import React from 'react';
import { useGoogleLogin } from '@react-oauth/google';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

interface LoginButtonProps {
  className?: string;
  children?: React.ReactNode;
}

export const LoginButton: React.FC<LoginButtonProps> = ({ className, children }) => {
  const login = useAppStore((state) => state.login);
  const [isLoading, setIsLoading] = React.useState(false);

  const handleGoogleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      setIsLoading(true);
      try {
        // Get ID token from Google
        const response = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
          headers: {
            Authorization: `Bearer ${tokenResponse.access_token}`,
          },
        });
        
        if (!response.ok) {
          throw new Error('Failed to fetch user info');
        }
        
        // For ID token, we need to use the credential response
        // Let's update the approach to use GoogleLogin component instead
        console.error('This approach needs ID token, not access token');
      } catch (error) {
        console.error('Google login error:', error);
        setIsLoading(false);
      }
    },
    onError: () => {
      console.error('Google login failed');
      setIsLoading(false);
    },
  });

  // Better approach: Use GoogleLogin component with ID token
  return (
    <button 
      onClick={handleGoogleLogin} 
      disabled={isLoading}
      className={className}
    >
      {isLoading ? '登入中...' : (children || '登入')}
    </button>
  );
};
```

**Better Implementation using `GoogleLogin` component:**

Create `src/components/auth/GoogleLoginButton.tsx`:

```typescript
import React, { useState } from 'react';
import { GoogleLogin, CredentialResponse } from '@react-oauth/google';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

interface GoogleLoginButtonProps {
  className?: string;
  children?: React.ReactNode;
}

export const GoogleLoginButton: React.FC<GoogleLoginButtonProps> = ({ className, children }) => {
  const login = useAppStore((state) => state.login);
  const [isLoading, setIsLoading] = useState(false);

  const handleSuccess = async (credentialResponse: CredentialResponse) => {
    if (!credentialResponse.credential) {
      console.error('No credential received from Google');
      return;
    }

    setIsLoading(true);
    try {
      // Send ID token to backend
      const authResponse = await authApi.verifyGoogleToken(credentialResponse.credential);
      
      // Store user and token in Zustand store
      login(
        {
          id: authResponse.user.id,
          name: authResponse.user.name,
          email: authResponse.user.email,
          avatar: authResponse.user.avatar || '',
          initials: authResponse.user.name
            .split(' ')
            .map(n => n[0])
            .join('')
            .toUpperCase()
            .slice(0, 2),
        },
        authResponse.token
      );
      
      console.log('Login successful');
    } catch (error) {
      console.error('Login failed:', error);
      alert('登入失敗，請稍後再試');
    } finally {
      setIsLoading(false);
    }
  };

  const handleError = () => {
    console.error('Google login error');
    setIsLoading(false);
  };

  return (
    <GoogleLogin
      onSuccess={handleSuccess}
      onError={handleError}
      useOneTap={false}
      theme="outline"
      size="large"
      text="signin_with"
      shape="rectangular"
      locale="zh_TW"
    />
  );
};
```

### Step 4: Update Auth API Service

Update `src/services/api/auth.ts`:

```typescript
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000/api';

export interface AuthResponse {
  user: {
    id: string;
    email: string;
    name: string;
    avatar?: string;
    google_id: string;
    email_verified: boolean;
    created_at: string;
    updated_at: string;
  };
  token: string;
}

export const authApi = {
  verifyGoogleToken: async (idToken: string): Promise<AuthResponse> => {
    try {
      const response = await axios.post<AuthResponse>(
        `${API_BASE_URL}/auth/google`,
        { idToken },
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
      return response.data;
    } catch (error: any) {
      if (axios.isAxiosError(error)) {
        const message = error.response?.data?.detail || error.message;
        throw new Error(`Authentication failed: ${message}`);
      }
      throw error;
    }
  },

  getCurrentUser: async (token: string): Promise<AuthResponse['user']> => {
    try {
      const response = await axios.get<AuthResponse['user']>(
        `${API_BASE_URL}/auth/me`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );
      return response.data;
    } catch (error: any) {
      if (axios.isAxiosError(error)) {
        const message = error.response?.data?.detail || error.message;
        throw new Error(`Failed to get user: ${message}`);
      }
      throw error;
    }
  },

  logout: async (): Promise<void> => {
    try {
      await axios.post(`${API_BASE_URL}/auth/logout`);
    } catch (error) {
      // Logout is handled client-side, so errors are non-critical
      console.warn('Logout request failed:', error);
    }
  },
};
```

### Step 5: Update UserMenu Component

Update `src/components/ui/UserMenu.tsx` to use the new Google login:

```typescript
// Replace LoginButton import
import { GoogleLoginButton } from '@/components/auth/GoogleLoginButton';

// In the component, replace LoginButton with GoogleLoginButton
{!user && (
  <GoogleLoginButton className="text-sm font-bold text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-300 dark:hover:text-white px-4 py-2 rounded-lg dark:hover:bg-slate-800 transition">
  </GoogleLoginButton>
)}
```

### Step 6: Add Axios Interceptor for Authentication (Optional)

Create `src/services/api/interceptors.ts`:

```typescript
import axios from 'axios';
import { useAppStore } from '@/store/useAppStore';

// Create axios instance
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:3000/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = useAppStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor to handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid
      useAppStore.getState().logout();
      // Optionally redirect to login
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);
```

### Step 7: Update Logout Functionality

Update the logout function in `src/components/ui/UserMenu.tsx`:

```typescript
import { authApi } from '@/services/api/auth';

const handleLogout = async () => {
  try {
    await authApi.logout();
  } catch (error) {
    console.warn('Logout request failed:', error);
  } finally {
    logout(); // Clear local state
  }
};
```

---

## Database Schema

### Users Table

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                    -- UUID
    google_id TEXT UNIQUE NOT NULL,         -- Google UID
    email TEXT UNIQUE NOT NULL,             -- User email
    name TEXT NOT NULL,                     -- Display name
    avatar TEXT,                            -- Profile picture URL
    email_verified BOOLEAN DEFAULT FALSE,   -- Email verification status
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_google_id ON users(google_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
```

### Migration

The user table will be automatically created when:
1. The auth router starts up (calls `init_user_table()`)
2. Or when you run the migration script: `python -m src.database.migrate`

---

## Security Considerations

### 1. Token Security

- **JWT Secret Key**: Use a strong, random secret key (minimum 32 characters)
  ```bash
  # Generate a secure random key
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

- **Token Expiration**: Set appropriate expiration times (default: 24 hours)
- **HTTPS**: Always use HTTPS in production

### 2. CORS Configuration

Ensure your backend CORS settings include your frontend domain:

```python
# In src/config.py
cors_origins: list[str] = [
    "http://localhost:5173",
    "https://your-production-domain.com",
]
```

### 3. Environment Variables

- Never commit `.env` files to git
- Use secure environment variable management in production (Render, Vercel, etc.)
- Rotate secrets regularly

### 4. Firebase Credentials

- Store Firebase service account JSON securely
- Use environment variables in production instead of file paths
- Never expose credentials in client-side code

### 5. Input Validation

- Always validate ID tokens on the backend
- Never trust client-side token validation
- Verify token expiration and signature

### 6. Rate Limiting (Future Enhancement)

Consider adding rate limiting to prevent abuse:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/google")
@limiter.limit("5/minute")
async def google_login(...):
    ...
```

---

## Testing

### Backend Testing

1. **Test Token Verification**
   ```bash
   # Start backend server
   python -m src.main
   
   # Test with curl (replace with actual ID token)
   curl -X POST http://localhost:3000/api/auth/google \
     -H "Content-Type: application/json" \
     -d '{"idToken": "your-google-id-token"}'
   ```

2. **Test Protected Endpoint**
   ```bash
   # Get JWT token from login response, then:
   curl -X GET http://localhost:3000/api/auth/me \
     -H "Authorization: Bearer your-jwt-token"
   ```

### Frontend Testing

1. **Test Google Login Flow**
   - Start frontend: `npm run dev`
   - Click "Login" button
   - Complete Google OAuth flow
   - Verify user is logged in
   - Check browser DevTools > Application > Local Storage for stored token

2. **Test Token Persistence**
   - Login
   - Refresh page
   - Verify user remains logged in

3. **Test Logout**
   - Click logout
   - Verify token is removed
   - Verify user is logged out

### Integration Testing

Create `tests/integration/test_auth.py`:

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_google_login_missing_token():
    response = client.post("/api/auth/google", json={})
    assert response.status_code == 400

def test_google_login_invalid_token():
    response = client.post("/api/auth/google", json={"idToken": "invalid-token"})
    assert response.status_code == 401

# Add more tests as needed
```

---

## Troubleshooting

### Backend Issues

**Problem: Firebase Admin SDK initialization fails**
- **Solution**: Check that `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON` is set correctly
- Verify the service account JSON file is valid
- Check Firebase project ID matches

**Problem: Token verification fails**
- **Solution**: Ensure Firebase project is properly configured
- Verify the ID token is not expired
- Check that the token is from the correct Google OAuth client

**Problem: Database errors**
- **Solution**: Run migration: `python -m src.database.migrate`
- Check database file permissions
- Verify database path in `.env`

### Frontend Issues

**Problem: Google login button doesn't appear**
- **Solution**: Check that `VITE_GOOGLE_CLIENT_ID` is set
- Verify `GoogleOAuthProvider` wraps your app
- Check browser console for errors

**Problem: "Invalid client" error**
- **Solution**: Verify Google Client ID matches the one in Google Cloud Console
- Check authorized JavaScript origins include your domain

**Problem: CORS errors**
- **Solution**: Add your frontend URL to backend `CORS_ORIGINS`
- Check that backend allows credentials: `allow_credentials=True`

**Problem: Token not persisting after refresh**
- **Solution**: Verify Zustand persist configuration includes `token` and `user`
- Check browser localStorage is not disabled

### Common Errors

**Error: "idToken is required"**
- Frontend is not sending the token correctly
- Check the request payload structure

**Error: "Firebase token verification failed"**
- Token is invalid or expired
- Firebase credentials are incorrect
- Token is from wrong OAuth client

**Error: "JWT_SECRET_KEY not configured"**
- Add `JWT_SECRET_KEY` to backend `.env`
- Generate a secure random key

---

## Next Steps

After implementing Google login, consider:

1. **User Profile Management**
   - Allow users to update their profile
   - Add user preferences/settings

2. **Protected Routes**
   - Add authentication middleware to protected API endpoints
   - Implement role-based access control (if needed)

3. **Session Management**
   - Add token refresh mechanism
   - Implement token blacklisting for logout

4. **Additional OAuth Providers**
   - Add Facebook, GitHub, or other providers
   - Create unified authentication interface

5. **Email Verification**
   - Send verification emails
   - Require verified emails for certain features

6. **Password Reset** (if adding email/password auth)
   - Implement password reset flow
   - Add email verification

---

## References

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Firebase Admin SDK Documentation](https://firebase.google.com/docs/admin/setup)
- [React OAuth Google Library](https://www.npmjs.com/package/@react-oauth/google)
- [FastAPI Security Documentation](https://fastapi.tiangolo.com/tutorial/security/)
- [JWT.io](https://jwt.io/) - For debugging JWT tokens

---

**Last Updated:** 2025-12-22  
**Author:** TinBoker Development Team

