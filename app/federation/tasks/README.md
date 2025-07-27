# Federation Task Handlers

This directory contains specialized task handlers for processing different ActivityPub activity types in the federation system.

## Overview

Each handler is responsible for processing a specific type of ActivityPub activity. Handlers are registered with the main federation processor and called when matching activities are received.

## Handler Structure

Each handler module should:
1. Inherit from `BaseHandler[T]` with appropriate type parameter
2. Implement the `can_handle()` method to identify supported activities
3. Implement the `handle()` method to process the activity
4. Handle errors gracefully and return appropriate status

## Available Handlers

### `create_handler.py`
Processes Create activities for new posts and comments.

### `follow_handler.py`
Handles Follow/Unfollow requests between users and communities.

### `like_handler.py`
Processes Like/Dislike (voting) activities.

### `announce_handler.py`
Handles Announce activities (boosts/shares).

## Adding New Handlers

1. Create a new file: `<activity_type>_handler.py`
2. Define the handler class:
```python
from app.federation.handlers import BaseHandler
from app.federation.types import ActivityObject, ProcessingResult

class MyHandler(BaseHandler[ActivityObject]):
    async def can_handle(self, activity: ActivityObject) -> bool:
        return activity.get('type') == 'MyType'
    
    async def handle(self, activity: ActivityObject) -> ProcessingResult:
        # Process the activity
        return ProcessingResult(success=True)
```

3. Register in `handlers.py`:
```python
from .tasks.my_handler import MyHandler
registry.register(MyHandler())
```

## Best Practices

1. **Type Safety**: Use proper type hints for all parameters and returns
2. **Error Handling**: Catch and log errors, return appropriate status
3. **Idempotency**: Handlers should be idempotent (safe to retry)
4. **Validation**: Validate activity structure before processing
5. **Performance**: Avoid blocking operations, use async where possible