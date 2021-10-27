from django.contrib.auth.decorators import login_required
from django.conf.urls import url

from .task import scorm_task

urlpatterns = (
    url(
        r'^runtask',
        scorm_task,
        name='scorm_task',
    ),
)