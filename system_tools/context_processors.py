"""
Template context processor that makes branding values available everywhere
as ``{{ branding.company_name }}`` etc. Safe for anonymous + admin pages.
"""

from .branding import get_branding


def branding(request):
    return {"branding": get_branding()}
