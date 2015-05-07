"""
Custom decorator for django-sudo.
"""
from functools import wraps

from sudo.settings import RESET_TOKEN
from sudo.utils import new_sudo_token_on_activity
from sudo.views import redirect_to_sudo


def sudo_required(func_or_region):
    """
    Enforces a view to have elevated privileges.
    Should likely be paired with ``@login_required``.

    >>> @sudo_required
    >>> def secure_page(request):
    >>>     ...

    Can also specify a particular sudo region (to only
    allow access to that region).

    Also get course_id, course_key_string and library_key_string
    from kwargs and set as region if region itself is None.

    >>> @sudo_required('admin_page')
    >>> def secure_admin_page(request):
    >>>     ...
    """
    def wrapper(func):  # pylint: disable=missing-docstring
        @wraps(func)
        def inner(request, *args, **kwargs):    # pylint: disable=missing-docstring
            course_specific_region = kwargs.get('course_id')
            if 'course_key_string' in kwargs:
                course_specific_region = kwargs.get('course_key_string')
            if 'library_key_string' in kwargs:
                course_specific_region = kwargs.get('library_key_string')
            if course_specific_region:
                course_specific_region = course_specific_region.replace(':', '').replace('/', '_').replace('+', '_')

            course_specific_region = course_specific_region.encode('utf-8', 'ignore')

            # N.B. region is captured from the enclosing sudo_required function
            if not request.is_sudo(region=region or course_specific_region):
                return redirect_to_sudo(request.get_full_path(), region=region or course_specific_region)

            if RESET_TOKEN is True:
                # Provide new sudo token content and reset timeout on activity
                new_sudo_token_on_activity(request, region=region or course_specific_region)

            return func(request, *args, **kwargs)
        return inner

    if callable(func_or_region):
        region = None
        return wrapper(func_or_region)
    else:
        region = func_or_region
        return wrapper
