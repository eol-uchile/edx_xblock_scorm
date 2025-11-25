# -*- coding: utf-8 -*-
import json

from ddt import ddt, data, unpack
from common.djangoapps.util.testing import UrlResetMixin
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from opaque_keys.edx.keys import CourseKey
from django.test import Client
from freezegun import freeze_time
from lms.djangoapps.instructor_task.models import InstructorTask
from .task import scorm_task
from common.djangoapps.student.tests.factories import UserFactory
import mock
from xblock.field_data import DictFieldData

from .scormxblock import ScormXBlock

class TestRequest(object):
    # pylint: disable=too-few-public-methods
    """
    Module helper for @json_handler
    """
    method = None
    body = None
    success = None
    POST = {}
    user = None
    META = {
        'REMOTE_ADDR': '',
        'HTTP_USER_AGENT': '',
        'SERVER_NAME':'',
        'HTTP_X_FORWARDED_PROTO': 'https'
    }
    get_host = mock.Mock()
    is_secure = mock.Mock()

@ddt
class ScormXBlockTests(UrlResetMixin, ModuleStoreTestCase):
    def setUp(self):
        super(ScormXBlockTests, self).setUp()
        self.user = UserFactory(username='uname', password='password', email='email@asd.com')
        self.client = Client()

    @staticmethod
    def make_one(**kw):
        """
        Creates a ScormXBlock for testing purpose.
        """
        field_data = DictFieldData(kw)
        runtime = kw.pop('runtime', mock.Mock())
        
        block = ScormXBlock(runtime, field_data, mock.Mock())
        block.location = mock.Mock(
            block_id="block_id", org="org", course="course", block_type="block_type"
        )
        return block

    def test_fields_xblock(self):
        block = self.make_one()
        self.assertEqual(block.display_name, "Scorm")
        self.assertEqual(block.scorm_file_meta, {})
        self.assertEqual(block.version_scorm, "SCORM_12")
        self.assertEqual(block.lesson_status, "not attempted")
        self.assertEqual(block.success_status, "unknown")
        self.assertEqual(block.data_scorm, {})
        self.assertEqual(block.lesson_score, 0)
        self.assertEqual(block.weight, 1)
        self.assertEqual(block.has_score, True)
        self.assertEqual(block.icon_class, "video")
        self.assertEqual(block.width, None)
        self.assertEqual(block.height, 650)
        self.assertEqual(block.task_id, '')
        self.assertEqual(block.task_token, '')

    def test_save_settings_scorm(self):
        block = self.make_one()

        fields = {
            "display_name": "Test Block",
            "has_score": "True",
            "file": None,
            "width": 800,
            "height": 450,
            "weight": 3.0,
            "task_step": "initial",
            "task_token": "asdf"
        }

        block.studio_submit(mock.Mock(method="POST", params=fields))
        self.assertEqual(block.display_name, fields["display_name"])
        self.assertEqual(block.has_score, fields["has_score"])
        self.assertEqual(block.icon_class, "problem")
        self.assertEqual(block.width, 800)
        self.assertEqual(block.height, 450)


    @freeze_time("2018-05-01")
    @mock.patch("scormxblock.scormxblock.os")
    @mock.patch("scormxblock.scormxblock.File", return_value="call_file")
    @mock.patch("scormxblock.scormxblock.get_scorm_storage")
    @mock.patch("scormxblock.ScormXBlock.get_sha1", return_value="sha1")
    def test_save_scorm_zipfile(
        self,
        get_sha1,
        default_storage,
        mock_file,
        mock_os,
    ):
        block = self.make_one()
        mock_file_object = mock.Mock()
        mock_file_object.configure_mock(name="scorm_file_name")
        default_storage.configure_mock(size=mock.Mock(return_value="1234"))
        mock_os.configure_mock(path=mock.Mock(join=mock.Mock(return_value="path_join"), splitext=mock.Mock(return_value="path_join")))

        fields = {
            "display_name": "Test Block",
            "has_score": "True",
            "file": mock.Mock(file=mock_file_object),
            "width": None,
            "height": 450,
            "weight": 3.0,
            "task_step": "initial",
            "task_token": "asdf"
        }

        block.studio_submit(mock.Mock(method="POST", params=fields))

        get_sha1.assert_called_once_with(mock_file_object)
        default_storage().save.assert_called_once_with('org/course/block_type/block_id/sha1a', "call_file")
        mock_file.assert_called_once_with(mock_file_object)

        expected_scorm_file_meta = {
            "sha1": "sha1",
            "name": "scorm_file_name",
            "last_updated": "2018-05-01T00:00:00.000000",
            "size": block.scorm_file_meta['size'], # can't patch seek() function
        }

        self.assertEqual(block.scorm_file_meta, expected_scorm_file_meta)

    def test_save_task_id(self):
        block = self.make_one()
        
        fields = {
            "task_id": "123-123-456"
        }

        block.save_task_id(mock.Mock(method="POST", params=fields))
        self.assertEqual(block.task_id, fields['task_id'])

    def test_submit_status(self):
        course_id = CourseKey.from_string('course-v1:eol+Test101+2021')
        task_type = 'SCORM'
        task_key = str(course_id)
        task_input = {}
        task = InstructorTask.create(course_id, task_type, task_key, task_input, self.user)
        block = self.make_one(task_id=task.task_id)
        expected_response = {'task_state': 'running'}
        response = block.studio_submit_status(mock.Mock(method="POST", params={}))
        self.assertEqual(json.loads(response.text), expected_response)

        task.task_state = 'FAILURE'
        task.save()
        expected_response = {'task_state': 'failure'}
        response = block.studio_submit_status(mock.Mock(method="POST", params={}))
        self.assertEqual(json.loads(response.text), expected_response)

        task.task_state = 'SUCCESS'
        task.save()
        expected_response = {'task_state': 'complete'}
        response = block.studio_submit_status(mock.Mock(method="POST", params={}))
        self.assertEqual(json.loads(response.text), expected_response)

        block = self.make_one()
        expected_response = {'task_state': 'error'}
        response = block.studio_submit_status(mock.Mock(method="POST", params={}))
        self.assertEqual(json.loads(response.text), expected_response)

    def test_build_file_storage_path(self):
        block = self.make_one(
            scorm_file_meta={"sha1": "sha1", "name": "scorm_file_name.html"}
        )

        file_storage_path = block.package_path

        self.assertEqual(file_storage_path, "org/course/block_type/block_id/sha1.html")

    @mock.patch("scormxblock.ScormXBlock._file_storage_path", return_value="file_storage_path")
    @mock.patch("scormxblock.scormxblock.default_storage")
    def test_student_view_data(self, default_storage, file_storage_path):
        mock_file_object = mock.Mock(name="scorm_file_name", **{"open.return_value": "1223454"})

        block = self.make_one(
            scorm_file_meta={"last_updated": "2018-05-01", "size": 1234},
            scorm_file="mock.Mock(return_value=mock_file_object)"
        )
        default_storage.configure_mock(url=mock.Mock(return_value="url_zip_file"))

        student_view_data = block.student_view_data()

        file_storage_path.assert_called_once_with()
        default_storage.url.assert_called_once_with("file_storage_path")
        self.assertEqual(
            student_view_data,
            {
                "last_modified": "2018-05-01",
                "scorm_data": "url_zip_file",
                "size": 1234,
                "index_page": None
            }
        )

    @mock.patch(
        "scormxblock.ScormXBlock.get_completion_status",
        return_value="completion_status",
    )
    @mock.patch("scormxblock.ScormXBlock.publish_grade")
    @data(
        {"name": "cmi.core.lesson_status", "value": "completed"},
        {"name": "cmi.completion_status", "value": "failed"},
        {"name": "cmi.success_status", "value": "unknown"},
    )
    def test_set_status(self, value, publish_grade, get_completion_status):
        block = self.make_one(has_score=True)

        response = block.scorm_set_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        publish_grade.assert_called_once_with()
        get_completion_status.assert_called_once_with()

        if value["name"] == "cmi.success_status":
            self.assertEqual(block.success_status, value["value"])
        else:
            self.assertEqual(block.lesson_status, value["value"])

        self.assertEqual(
            response.json,
            {
                "completion_status": "completion_status",
                "lesson_score": 0,
                "result": "success",
            },
        )

    @mock.patch(
        "scormxblock.ScormXBlock.get_completion_status",
        return_value="completion_status",
    )
    @data(
        {"name": "cmi.core.score.raw", "value": "20"},
        {"name": "cmi.score.raw", "value": "20"},
    )
    def test_set_lesson_score(self, value, get_completion_status):
        block = self.make_one(has_score=True)

        response = block.scorm_set_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        get_completion_status.assert_called_once_with()

        self.assertEqual(block.lesson_score, 0.2)

        self.assertEqual(
            response.json,
            {
                "completion_status": "completion_status",
                "lesson_score": 0.2,
                "result": "success",
            },
        )

    @mock.patch(
        "scormxblock.ScormXBlock.get_completion_status",
        return_value="completion_status",
    )
    @data(
        {"name": "cmi.core.lesson_location", "value": 1},
        {"name": "cmi.location", "value": 2},
        {"name": "cmi.suspend_data", "value": [1, 2]},
    )
    def test_set_other_scorm_values(self, value, get_completion_status):
        block = self.make_one(has_score=True)

        response = block.scorm_set_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        get_completion_status.assert_called_once_with()

        self.assertEqual(block.data_scorm[value["name"]], value["value"])

        self.assertEqual(
            response.json,
            {"completion_status": "completion_status", "result": "success"},
        )

    @data(
        {"name": "cmi.core.lesson_status"},
        {"name": "cmi.completion_status"},
        {"name": "cmi.success_status"},
    )
    def test_scorm_get_status(self, value):
        block = self.make_one(lesson_status="status", success_status="status")

        response = block.scorm_get_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        self.assertEqual(response.json, {"value": "status"})

    @data(
        {"name": "cmi.core.score.raw"}, {"name": "cmi.score.raw"},
    )
    def test_scorm_get_lesson_score(self, value):
        block = self.make_one(lesson_score=0.2)

        response = block.scorm_get_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        self.assertEqual(response.json, {"value": 20})

    @data(
        {"name": "cmi.core.lesson_location"},
        {"name": "cmi.location"},
        {"name": "cmi.suspend_data"},
    )
    def test_get_other_scorm_values(self, value):
        block = self.make_one(
            data_scorm={
                "cmi.core.lesson_location": 1,
                "cmi.location": 2,
                "cmi.suspend_data": [1, 2],
            }
        )

        response = block.scorm_get_value(
            mock.Mock(method="POST", body=json.dumps(value).encode('utf-8'))
        )

        self.assertEqual(response.json, {"value": block.data_scorm[value["name"]]})
    
    @data(
        ({"name": "cmi.core.student_id"}, "edx-platform.user_id", 23),
        ({"name": "cmi.core.student_name"}, "edx-platform.username", "supername")
    )
    @unpack
    def test_scorm_get_student_data(self, request_data, key, value):
        service_user_mock = mock.Mock()
        current_user_mock = mock.Mock()
        current_user_mock.opt_attrs = {
            key : value
        }
        service_user_mock.configure_mock(**{"get_current_user.return_value": current_user_mock})

        runtime = mock.Mock()
        runtime.service.return_value = service_user_mock

        block = self.make_one(runtime=runtime)

        response = block.scorm_get_value(
            mock.Mock(method="POST", body=json.dumps(request_data))
        )
        self.assertEqual(response.json, {"value": value})
        

    @mock.patch("scormxblock.task.validate_token", return_value=True)
    def test_scorm_task(self, mock_validate):
        post_data = {
            "extract_folder_path": "folder/path",
            "package_path": "path",
            "token": "123",
            "course_id": "course-v1:eol+Test101+2021",
            "block_id": "block-v1:eol+Test101+2021+type@scormxblock+block@189368e38e4e404686e514e95cd4749e",
        }
        request = TestRequest()
        request.method = "POST"
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        r = json.loads(result._container[0].decode())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(r["status"], "Running")

    def test_scorm_task_wrong_method(self):
        post_data = {
            "extract_folder_path": "folder/path",
            "package_path": "path",
            "token": "123",
            "course_id": "course-v1:eol+Test101+2021",
            "block_id": "block-v1:eol+Test101+2021+type@scormxblock+block@189368e38e4e404686e514e95cd4749e",
        }
        request = TestRequest()
        request.method = "GET"
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        self.assertEqual(result.status_code, 400)

    def test_scorm_task_miss_params(self):
        post_data = {
            "extract_folder_path": "folder/path",
            "token": "123",
            "course_id": "course-v1:eol+Test101+2021",
            "block_id": "block-v1:eol+Test101+2021+type@scormxblock+block@189368e38e4e404686e514e95cd4749e",
        }
        request = TestRequest()
        request.method = "POST"
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        self.assertEqual(result.status_code, 400)

    def test_scorm_task_wrong_course_id(self):
        post_data = {
            "extract_folder_path": "folder/path",
            "package_path": "path",
            "token": "123",
            "course_id": "asdasdasd",
            "block_id": "block-v1:eol+Test101+2021+type@scormxblock+block@189368e38e4e404686e514e95cd4749e",
        }
        request = TestRequest()
        request.method = "POST"
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        self.assertEqual(result.status_code, 400)

    def test_scorm_task_wrong_block_id(self):
        post_data = {
            "extract_folder_path": "folder/path",
            "package_path": "path",
            "token": "123",
            "course_id": "course-v1:eol+Test101+2021",
            "block_id": "asdasdasdasd",
        }
        request = TestRequest()
        request.method = "POST"
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        self.assertEqual(result.status_code, 400)

    @mock.patch("scormxblock.task.validate_token", return_value=False)
    def test_scorm_task_wrong_token(self, mock_validate):
        post_data = {
            "extract_folder_path": "folder/path",
            "package_path": "path",
            "token": "456",
            "course_id": "course-v1:eol+Test101+2021",
            "block_id": "block-v1:eol+Test101+2021+type@scormxblock+block@189368e38e4e404686e514e95cd4749e",
        }
        request = TestRequest()
        request.method = 'POST'
        request.POST = post_data
        request.user = self.user
        result = scorm_task(request)
        self.assertEqual(result.status_code, 400)
