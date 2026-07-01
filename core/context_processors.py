from django.conf import settings


def drc_match_banner(request):
    return {
        "show_drc_match_banner": settings.SHOW_DRC_MATCH_BANNER,
    }
