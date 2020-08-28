from django.conf import settings
from django.core.files.storage import get_storage_class

import logging
logger = logging.getLogger(__name__)

def get_scorm_storage():
  """
  Get the default storage for SCORM objects
  """
  return get_storage_class(settings.SCORM_STORAGE_CLASS['class'])(**settings.SCORM_STORAGE_CLASS['options'])