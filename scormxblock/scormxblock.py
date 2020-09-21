import json
import hashlib
import re
import os
import logging
import pkg_resources
import xml.etree.ElementTree as ET
import zipfile
import os.path

from django.core.files import File
from django.core.files.base import ContentFile
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile, InMemoryUploadedFile
from django.conf import settings
from django.template import Context, Template
from django.utils import timezone
from webob import Response

from xblock.core import XBlock
from xblock.fields import Scope, String, Float, Boolean, Dict, DateTime, Integer
from xblock.fragment import Fragment

from .utils import get_scorm_storage

from xmodule.util.duedate import get_extended_due_date
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Make '_' a no-op so we can scrape strings
_ = lambda text: text

@XBlock.wants("settings")
class ScormXBlock(XBlock):

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="Scorm",
        scope=Scope.settings,
    )
    scorm_file = String(
        display_name=_("Upload scorm file"),
        scope=Scope.settings,
    )
    path_index_page = String(
        display_name=_("Path to the index page in scorm file"),
        scope=Scope.settings,
    )
    scorm_file_meta = Dict(
        scope=Scope.content
    )
    version_scorm = String(
        default="SCORM_12",
        scope=Scope.settings,
    )
    # save completion_status for SCORM_2004
    lesson_status = String(
        scope=Scope.user_state,
        default='not attempted'
    )
    success_status = String(
        scope=Scope.user_state,
        default='unknown'
    )
    data_scorm = Dict(
        scope=Scope.user_state,
        default={}
    )
    lesson_score = Float(
        scope=Scope.user_state,
        default=0
    )
    weight = Integer(
        display_name=_('Weight'),
        help=_("Weight of this Scorm, by default keep 1"),
        default=1,
        values={"min": 0, "step": 1},
        scope=Scope.settings
    )
    has_score = Boolean(
        display_name=_("Scored"),
        help=_("Select False if this component will not receive a numerical score from the Scorm"),
        default=True,
        scope=Scope.settings
    )
    icon_class = String(
        default="video",
        scope=Scope.settings,
    )
    width = Integer(
        display_name=_("Display Width (px)"),
        help=_('Width of iframe, if empty, the default 100%'),
        scope=Scope.settings
    )
    height = Integer(
        display_name=_("Display Height (px)"),
        help=_('Height of iframe'),
        default=650,
        scope=Scope.settings
    )

    has_author_view = True

    def render_template(self, template_path, context):
        template_str = self.resource_string(template_path)
        template = Template(template_str)
        return template.render(Context(context))

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None):
        student_context = {
            "index_page_url": self.get_live_url(),
            "completion_status": self.get_completion_status(),
            "grade": self.get_grade(),
            "scorm_xblock": self,
        }
        student_context.update(context or {})
        template = self.render_template("static/html/scormxblock.html", student_context)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/scormxblock.js"))
        frag.initialize_js(
            "ScormXBlock", json_args={"version_scorm": self.version_scorm}
        )
        return frag
    

    def studio_view(self, context=None):
        # Note that we cannot use xblockutils's StudioEditableXBlockMixin because we
        # need to support package file uploads.
        studio_context = {
            "field_display_name": self.fields["display_name"],
            "field_has_score": self.fields["has_score"],
            "field_weight": self.fields["weight"],
            "field_width": self.fields["width"],
            "field_height": self.fields["height"],
            "scorm_xblock": self,
        }
        studio_context.update(context or {})
        template = self.render_template("static/html/studio.html", studio_context)
        frag = Fragment(template)
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.initialize_js("ScormStudioXBlock")
        return frag

    def author_view(self, context=None):
        context = context or {}
        if not self.path_index_page:
            context["message"] = "Aún no se sube ningún archivo SCORM. Edite el componente para configurar."
        else:
            context["message"] = "El componente SCORM solo estará visible en el LMS."
        html = self.render_template("static/html/author_view.html", context)
        frag = Fragment(html)
        return frag

    @staticmethod
    def json_response(data):
        return Response(
            json.dumps(data), content_type="application/json", charset="utf8"
        )

    @XBlock.handler
    def studio_submit(self, request, suffix=''):
        self.display_name = request.params['display_name']
        self.width = request.params['width']
        self.height = request.params['height']
        self.has_score = request.params['has_score']
        self.weight = request.params['weight']
        self.icon_class = 'problem' if self.has_score == 'True' else 'video'

        response = {"result": "success", "errors": []}
        if not hasattr(request.params["file"], "file"):
            # File not uploaded
            return self.json_response(response)

        package_file = request.params["file"].file
        package_data = package_file.read()
        self.update_package_meta(package_file)

        # Clone zip file before django closes it when uploaded
        if isinstance(package_file, InMemoryUploadedFile):
            package_file = SimpleUploadedFile(
                package_file.name,
                package_data,
                package_file.content_type
            )

        # First, save scorm file in the storage for mobile clients
        storage = get_scorm_storage()
        storage.save(self.package_path, File(package_file))
        logger.info('Scorm "%s" file stored at "%s"', package_file, self.package_path)

        # Then, extract zip file
        if isinstance(package_file, InMemoryUploadedFile):
            package_file = SimpleUploadedFile(
                package_file.name,
                package_data,
                package_file.content_type
            )

        with zipfile.ZipFile(package_file, "r") as scorm_zipfile:
            for zipinfo in scorm_zipfile.infolist():
                if os.path.splitext(zipinfo.filename)[1] in ["html", "html5", "css", "js"]:
                    storage.save(
                        os.path.join(self.extract_folder_path, zipinfo.filename),
                        ContentFile(scorm_zipfile.open(zipinfo.filename).read().encode())
                        )
                else:
                    storage.save(
                        os.path.join(self.extract_folder_path, zipinfo.filename),
                        ContentFile(scorm_zipfile.open(zipinfo.filename).read())
                        )
        try:
            self.update_package_fields()
        except ScormError as e:
            response["errors"].append(e.args[0])

        return self.json_response(response)

    @property
    def package_path(self):
        """
        Get file path of storage.
        """
        return (
            "{loc.org}/{loc.course}/{loc.block_type}/{loc.block_id}/{sha1}{ext}"
        ).format(
            loc=self.location,
            sha1=self.scorm_file_meta["sha1"],
            ext=os.path.splitext(self.scorm_file_meta["name"])[1],
        )

    @property
    def extract_folder_path(self):
        """
        This path needs to depend on the content of the scorm package. Otherwise,
        served media files might become stale when the package is update.
        """
        return os.path.join(self.extract_folder_base_path, self.scorm_file_meta["sha1"])

    @property
    def extract_folder_base_path(self):
        """
        Path to the folder where packages will be extracted.
        """
        return os.path.join(self.scorm_location(), self.location.block_id)

    @XBlock.json_handler
    def scorm_get_value(self, data, suffix=''):
        name = data.get('name')
        if name in ['cmi.core.lesson_status', 'cmi.completion_status']:
            return {'value': self.lesson_status}
        elif name == 'cmi.success_status':
            return {'value': self.success_status}
        elif name in ['cmi.core.score.raw', 'cmi.score.raw']:
            return {'value': self.lesson_score * 100}
        else:
            return {'value': self.data_scorm.get(name, '')}

    @XBlock.json_handler
    def scorm_set_value(self, data, suffix=''):
        context = {'result': 'success'}
        name = data.get('name')

        if not self.is_past_due():
            if name in ['cmi.core.lesson_status', 'cmi.completion_status']:
                self.lesson_status = data.get('value')
                if self.has_score and data.get('value') in ['completed', 'failed', 'passed']:
                    self.publish_grade()
                    context.update({"lesson_score": self.lesson_score})

            elif name == 'cmi.success_status':
                self.success_status = data.get('value')
                if self.has_score:
                    if self.success_status == 'unknown':
                        self.lesson_score = 0
                    self.publish_grade()
                    context.update({"lesson_score": self.lesson_score})
            elif name in ['cmi.core.score.raw', 'cmi.score.raw'] and self.has_score:
                self.lesson_score = float(data.get('value', 0))/100.0 * self.weight
                self.publish_grade()
                context.update({"lesson_score": self.lesson_score})
            else:
                self.data_scorm[name] = data.get('value', '')

        context.update({"completion_status": self.get_completion_status()})
        return context

    def get_grade(self):
        lesson_score = self.lesson_score
        if self.lesson_status == "failed" or (
            self.version_scorm == "SCORM_2004"
            and self.success_status in ["failed", "unknown"]
        ):
            lesson_score = 0
        return lesson_score

    def set_score(self, score):
        """
        Utility method used to rescore a problem.
        """
        self.lesson_score = score.raw_earned / self.weight
    
    def is_past_due(self):
        """
        Return whether due date has passed.
        """
        due = get_extended_due_date(self)
        try:
            graceperiod = self.graceperiod
        except AttributeError:
            # graceperiod and due are defined in InheritanceMixin
            # It's used automatically in edX but the unit tests will need to mock it out
            graceperiod = None
            
        if graceperiod is not None and due:
            close_date = due + graceperiod
        else:
            close_date = due
        
        if close_date is not None:
            return datetime.now(tz=pytz.utc) > close_date
        return False
    
    def publish_grade(self):
        self.runtime.publish(
            self,
            'grade',
            {
                'value': self.lesson_score,
                'max_value': self.weight,
            })
    
    def max_score(self):
        """
        Return the maximum score possible.
        """
        return self.weight if self.has_score else None
    
    def update_package_meta(self, package_file):
        self.scorm_file_meta["sha1"] = self.get_sha1(package_file)
        self.scorm_file_meta["name"] = package_file.name
        self.scorm_file_meta["last_updated"] = timezone.now().strftime(
            DateTime.DATETIME_FORMAT
        )
        self.scorm_file_meta["size"] = package_file.seek(0, 2)
        package_file.seek(0)

    def update_package_fields(self):
        """
        Update version and index page path fields.
        """
        self.path_index_page = ""
        imsmanifest_path = os.path.join(self.extract_folder_path, "imsmanifest.xml")
        try:
            imsmanifest_file = get_scorm_storage().open(imsmanifest_path)
        except IOError:
            raise ScormError(
                "Invalid package: could not find 'imsmanifest.xml' file at the root of the zip file"
            )
        else:
            tree = ET.parse(imsmanifest_file)
            imsmanifest_file.seek(0)
            self.path_index_page = "index.html"
            namespace = ""
            for _, node in ET.iterparse(imsmanifest_file, events=["start-ns"]):
                if node[0] == "":
                    namespace = node[1]
                    break
            root = tree.getroot()

            if namespace:
                resource = root.find(
                    "{{{0}}}resources/{{{0}}}resource".format(namespace)
                )
                schemaversion = root.find(
                    "{{{0}}}metadata/{{{0}}}schemaversion".format(namespace)
                )
            else:
                resource = root.find("resources/resource")
                schemaversion = root.find("metadata/schemaversion")

            if resource:
                self.path_index_page = resource.get("href")
            if (schemaversion is not None) and (
                re.match("^1.2$", schemaversion.text) is None
            ):
                self.version_scorm = "SCORM_2004"
            else:
                self.version_scorm = "SCORM_12"


    def get_completion_status(self):
        completion_status = self.lesson_status
        if self.version_scorm == "SCORM_2004" and self.success_status != "unknown":
            completion_status = self.success_status
        return completion_status

    def scorm_location(self):
        """
        Unzipped files will be stored in a media folder with this name, and thus
        accessible at a url with that also includes this name.
        """
        default_scorm_location = "scorm"
        settings_service = self.runtime.service(self, "settings")
        if not settings_service:
            return default_scorm_location
        xblock_settings = settings_service.get_settings_bucket(self)
        return xblock_settings.get("LOCATION", default_scorm_location)

    def get_live_url(self):
        """
        Get the url of the index page of the scorm
        """
        if not self.scorm_file_meta:
            return ''
        if self.scorm_file:
            # old files - deprecated
            return reverse('scormxblock:scorm-proxy-deprecated', kwargs={'block_id': self.location.block_id, 'file': self.path_index_page})
        return reverse('scormxblock:scorm-proxy', kwargs={'block_id': self.location.block_id, 'sha1': self.scorm_file_meta["sha1"], 'file': self.path_index_page})
    
    @staticmethod
    def get_sha1(file_descriptor):
        """
        Get file hex digest (fingerprint).
        """
        block_size = 8 * 1024
        sha1 = hashlib.sha1()
        while True:
            block = file_descriptor.read(block_size)
            if not block:
                break
            sha1.update(block)
        file_descriptor.seek(0)
        return sha1.hexdigest()
    
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("ScormXBlock",
             """<vertical_demo>
                <scormxblock/>
                </vertical_demo>
             """),
        ]
class ScormError(Exception):
    pass