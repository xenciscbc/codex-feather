`retry_delay(attempt)` accepts a non-negative integer and returns `min(2 ** attempt, 8)`. It raises `ValueError` for all other inputs.
