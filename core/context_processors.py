from django.conf import settings


def independence_banner(request):
    return {
        "show_independence_banner": settings.SHOW_INDEPENDENCE_BANNER,
    }
