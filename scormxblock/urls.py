from django.contrib.auth.decorators import login_required
from django.conf.urls import url

from .views import proxy_scorm_media

urlpatterns = (
    url(
        r'^v0/(?P<block_id>[\w\-]+)\/(?P<file>.*)',
        proxy_scorm_media,
        name='scorm-proxy-deprecated',
    ),
    url(
        r'^v1/(?P<block_id>[\w\-]+)\/(?P<sha1>[\w\-]+)\/(?P<file>.*)',
        proxy_scorm_media,
        name='scorm-proxy',
    ),
)