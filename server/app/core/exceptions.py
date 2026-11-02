class JobNotFoundError(Exception):
    """Raised when a job is not found or the user is not authorized to access it."""
    pass

class RecruiterNotFoundError(Exception):
    """Raised when a recruiter profile does not exist for the given user."""
    pass