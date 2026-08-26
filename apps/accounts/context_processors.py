def role(request):
    """Expose the profile to every template without a get_or_create in each view."""
    profile = None
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        profile = getattr(user, "profile", None)
    return {"profile": profile}
