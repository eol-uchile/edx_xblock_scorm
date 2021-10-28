# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import six
import json
import os
import math
import logging
from django.conf import settings
from opaque_keys.edx.keys import CourseKey, UsageKey
from opaque_keys import InvalidKeyError
from django.contrib.auth.models import User
from opaque_keys.edx.locator import CourseLocator, BlockUsageLocator

from celery import current_task, task
from lms.djangoapps.instructor_task.tasks_base import BaseInstructorTask
from lms.djangoapps.instructor_task.api_helper import submit_task
from lms.djangoapps.instructor_task.tasks_helper.runner import run_main_task, TaskProgress
from django.db import IntegrityError, transaction
from functools import partial
from time import time
from django.utils.translation import ugettext_noop
from lms.djangoapps.instructor_task.api_helper import AlreadyRunningError
from django.core.files.storage import get_storage_class
from xmodule.modulestore.django import modulestore
import zipfile
import os.path
from django.core.files.base import ContentFile
from .utils import get_scorm_storage
from django.http import HttpResponse
from common.djangoapps.util.json_request import JsonResponse, expect_json
logger = logging.getLogger(__name__)

def extract_zipfile(extract_folder_path, package_path):
    """
        Extract zipfile and save in storage
    """
    storage = get_scorm_storage()
    package_file = storage.open(package_path)
    with zipfile.ZipFile(package_file, "r") as scorm_zipfile:
        for zipinfo in scorm_zipfile.infolist():
            content_file = ContentFile(scorm_zipfile.open(zipinfo.filename).read())
            if os.path.splitext(zipinfo.filename)[-1] in ["js", ".js"]:
                content_file.content_type = 'text/javascript' # fix b'text/javascript'
            storage.save(
                os.path.join(extract_folder_path, zipinfo.filename),
                content_file
                )

@task(base=BaseInstructorTask)
def process_data(entry_id, xmodule_instance_args):
    action_name = ugettext_noop('generated')
    task_fn = partial(task_get_data, xmodule_instance_args)
    return run_main_task(entry_id, task_fn, action_name)

def task_get_data(
        _xmodule_instance_args,
        _entry_id,
        course_id,
        task_input,
        action_name):
    course_key = course_id
    #user_id = task_input['user']
    start_time = time()
    task_progress = TaskProgress(action_name, 1, start_time)
    extract_zipfile(task_input['extract_folder_path'], task_input['package_path'])
    current_step = {'step': 'Uploading Scorm'}
    return task_progress.update_task_state(extra_meta=current_step)

def task_process_data(request, course_id, extract_folder_path, package_path):
    course_key = CourseKey.from_string(course_id)
    task_type = 'SCORM'
    task_class = process_data
    task_input = {'course_id': course_id, 'extract_folder_path': extract_folder_path, 'package_path':package_path}
    task_key = "{}".format(course_id)
    return submit_task(
        request,
        task_type,
        task_class,
        course_key,
        task_input,
        task_key)

@transaction.non_atomic_requests
def scorm_task(request):
    """
        Create task to extract and read zipfile
    """
    if request.method != "POST":
        logger.error("Scorm - Error method request: {}".format(request.method))
        return HttpResponse(status=400)
    if request.user.is_anonymous:
        logger.error("Scorm - User is Anonymous")
        return HttpResponse(status=400)
    if 'extract_folder_path' not in request.POST or 'package_path' not in request.POST or 'course_id' not in request.POST or 'block_id' not in request.POST or 'token' not in request.POST:
        logger.error("Scorm - Error with params in POST")
        return HttpResponse(status=400)
    try:
        course_key = CourseKey.from_string(request.POST['course_id'])
        block_id = UsageKey.from_string(request.POST['block_id'])
    except InvalidKeyError:
        logger.error("Scorm - Error with course_id or usage_key, course_id {}, usage_key: {}".format(request.POST['course_id'], request.POST['block_id']))
        return HttpResponse(status=400)
    
    if not validate_token(course_key, request.POST['token'], block_id):
        return HttpResponse(status=400)
    try:
        task = task_process_data(request, request.POST.get('course_id'), request.POST.get('extract_folder_path'), request.POST.get('package_path'))
        return JsonResponse({'status': 'Running', 'task_id':task.task_id}, status=200)
    except AlreadyRunningError:
        logger.info("Scorm - Task Already Running Error, course_id: {}".format(request.POST['course_id']))
        return JsonResponse({'status': 'AlreadyRunning'}, status=200)

def validate_token(course_key, token, block_id):
    """
        Verify if token is correct
    """
    store = modulestore()
    with store.bulk_operations(course_key):
        source_item = store.get_item(block_id)
        if source_item.task_token != token:
            logger.error("Scorm - Error with token: {}".format(request.POST['token']))
            return False
        else:
            return True