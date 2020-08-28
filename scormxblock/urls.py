from django.contrib.auth.decorators import login_required
from django.conf.urls import url

from .views import proxy_scorm_media

urlpatterns = (
    url(
        r'^(?P<block_id>[\w\-]+)\/(?P<sha1>[\w\-]+)\/(?P<file>.*)',
        proxy_scorm_media,
        name='scorm-proxy',
    ),
)