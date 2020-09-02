import os.path
import mimetypes

from django.http import HttpResponse

from .utils import get_scorm_storage

import logging

logger = logging.getLogger(__name__)

def proxy_scorm_media(request, block_id, file, sha1=None):
    """
    Render the media objects by proxy, as the files
    must be in the same domain as the LMS
    """
    guess = mimetypes.guess_type(file)
    if guess[0] is None:
      content_type = "text/html"
    else:
      content_type = guess[0]

    if sha1:
      location = "scorm/{}/{}/{}".format(block_id, sha1, file)
    else:
      location = "scorm/{}/{}".format(block_id, file)

    return HttpResponse(
      get_scorm_storage().open(location).read(),
      content_type=content_type,
    ) 