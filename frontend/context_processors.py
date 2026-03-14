"""Context processors for the frontend app."""


def frontend_context(request):
    """Add common frontend context variables to all templates."""
    user = request.user
    ctx = {
        "is_authenticated": user.is_authenticated,
        "is_candidate": False,
        "is_recruiter": False,
        "current_user": None,
    }
    if user.is_authenticated:
        ctx["current_user"] = user
        ctx["is_candidate"] = user.role == "candidate"
        ctx["is_recruiter"] = user.role == "recruiter"
    return ctx
