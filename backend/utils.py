"""Utility functions for consistent error handling and responses"""

def safe_query_or_404(model, id, user_id=None):
    """Query with optional user ownership check"""
    obj = model.query.get(id)
    if not obj:
        return None, {'error': 'Not found'}, 404
    if user_id and hasattr(obj, 'user_id') and obj.user_id != user_id:
        return None, {'error': 'Unauthorized'}, 403
    return obj, None, None


def safe_list_query(query_func):
    """Execute query and return empty list on error"""
    try:
        return query_func()
    except Exception as e:
        print(f"Query error: {e}")
        return []


def safe_file_operation(operation, filepath, default=None):
    """Execute file operation with error handling"""
    try:
        return operation(filepath)
    except Exception as e:
        print(f"File operation error on {filepath}: {e}")
        return default
