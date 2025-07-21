# Campus API Gaps and Planned Endpoints

This document outlines missing server endpoints identified during the client-server API alignment analysis, along with planned implementations.

## Campus Apps Service - Missing Endpoints

### Users Resource

#### List All Users
```
GET /users
```
**Purpose**: List all users with optional filtering and pagination
**Client Support**: ✅ `users.list()` (already implemented)
**Status**: 🔄 Planned for server implementation

**Request Parameters**:
- `limit` (optional): Maximum number of users to return
- `offset` (optional): Number of users to skip for pagination
- `search` (optional): Search query for filtering users

**Response Format**:
```json
{
  "users": [
    {
      "id": "user_123",
      "email": "user@example.com", 
      "name": "User Name",
      "created_at": "2025-07-21T10:30:00Z"
    }
  ],
  "total": 150,
  "limit": 20,
  "offset": 0
}
```

### Circles Resource

#### List All Circles
```
GET /circles
```
**Purpose**: List all circles with optional filtering and pagination
**Client Support**: ✅ `circles.list()` (already implemented) 
**Status**: 🔄 Planned for server implementation

**Request Parameters**:
- `limit` (optional): Maximum number of circles to return
- `offset` (optional): Number of circles to skip for pagination

**Response Format**:
```json
{
  "circles": [
    {
      "id": "circle_123",
      "name": "Circle Name",
      "description": "Circle description",
      "owner_id": "user_456",
      "created_at": "2025-07-21T10:30:00Z"
    }
  ],
  "total": 50,
  "limit": 20,
  "offset": 0
}
```

#### Search Circles
```
GET /circles/search?q={query}
```
**Purpose**: Search circles by name, description, or other criteria
**Client Support**: ✅ `circles.search(query)` (already implemented)
**Status**: 🔄 Planned for server implementation

**Request Parameters**:
- `q` (required): Search query string

**Response Format**:
```json
{
  "circles": [
    {
      "id": "circle_123",
      "name": "Matching Circle",
      "description": "Description with matching terms",
      "owner_id": "user_456",
      "created_at": "2025-07-21T10:30:00Z"
    }
  ]
}
```

#### List Circles by User
```
GET /users/{user_id}/circles
```
**Purpose**: List all circles that a user is a member of
**Client Support**: ✅ `circles.list_by_user(user_id)` (already implemented)
**Status**: 🔄 Planned for server implementation

**Response Format**:
```json
{
  "circles": [
    {
      "id": "circle_123",
      "name": "Circle Name",
      "description": "Circle description",
      "role": "member",
      "joined_at": "2025-07-20T15:30:00Z"
    }
  ]
}
```

## Unimplemented Server Endpoints (Return 501)

### Move Circle
```
POST /circles/{circle_id}/move
```
**Current Status**: Returns 501 Not Implemented
**Client Support**: ❌ Not implemented (should be added)
**Priority**: 🔄 Medium

**Request Body**:
```json
{
  "parent_circle_id": "circle_456"
}
```

### Get Circle Users
```
GET /circles/{circle_id}/users
```
**Current Status**: Returns 501 Not Implemented  
**Client Support**: ❌ Not implemented (should be added)
**Priority**: 🔄 Medium

**Response Format**:
```json
{
  "users": [
    {
      "id": "user_123",
      "email": "user@example.com",
      "name": "User Name",
      "role": "member",
      "joined_at": "2025-07-20T15:30:00Z"
    }
  ]
}
```

## Implementation Priority

### High Priority (Client methods exist, server missing)
1. `GET /users` - List all users
2. `GET /circles` - List all circles  
3. `GET /circles/search` - Search circles
4. `GET /users/{user_id}/circles` - List user's circles

### Medium Priority (Recently Implemented in Client)
1. `POST /circles/{circle_id}/move` - Move circle ✅ `circle.move(parent_id)` 
2. `GET /circles/{circle_id}/users` - Get circle users ✅ `circle.get_users()`
3. `PATCH /users/{user_id}` - Update user ✅ `user.update(**kwargs)`
4. `DELETE /users/{user_id}` - Delete user ✅ `user.delete()`
5. `GET /users/{user_id}/profile` - Get user profile ✅ `user.get_profile()`

### Notes
- All high-priority endpoints have working client implementations
- Medium-priority client methods have been implemented to match server API patterns
- Server implementations should follow the response formats specified
- Error handling should be consistent with existing endpoints
- Authentication and authorization should follow existing patterns
- BaseClient now supports PATCH requests for update operations
