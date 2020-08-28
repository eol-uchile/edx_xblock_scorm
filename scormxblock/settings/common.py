""" Common settings for scormxblock. """
import base64


def plugin_settings(settings):
    settings.SCORM_STORAGE_CLASS = {
      'class': '',
      'options': {
        'location': 'scorm',
      }
    }