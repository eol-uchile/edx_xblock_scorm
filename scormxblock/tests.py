# -*- coding: utf-8 -*-
import json
import unittest


from ddt import ddt, data
from freezegun import freeze_time
import mock
from xblock.field_data import DictFieldData

from .scormxblock import ScormXBlock


@ddt
class ScormXBlockTests(unittest.TestCase):
    @staticmethod
    def make_one(**kw):
        """
        Creates a ScormXBlock for testing purpose.
        """
        field_data = DictFieldData(kw)
        block = ScormXBlock(mock.Mock(), field_data, mock.Mock())
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

    def test_save_settings_scorm(self):
        block = self.make_one()

        fields = {
            "display_name": "Test Block",
            "has_score": "True",
            "file": None,
            "width": 800,
            "height": 450,
            "weight": 3.0,
        }

        block.studio_submit(mock.Mock(method="POST", params=fields))
        self.assertEqual(block.display_name, fields["display_name"])
        self.assertEqual(block.has_score, fields["has_score"])
        self.assertEqual(block.icon_class, "problem")
        self.assertEqual(block.width, 800)
        self.assertEqual(block.height, 450)


    @freeze_time("2018-05-01")
    @mock.patch("scormxblock.ScormXBlock.update_package_fields")
    @mock.patch("scormxblock.scormxblock.os")
    @mock.patch("scormxblock.scormxblock.zipfile")
    @mock.patch("scormxblock.scormxblock.File", return_value="call_file")
    @mock.patch("scormxblock.scormxblock.get_scorm_storage")
    @mock.patch(
        "scormxblock.ScormXBlock.package_path", return_value="package_path"
    )
    @mock.patch("scormxblock.ScormXBlock.get_sha1", return_value="sha1")
    def test_save_scorm_zipfile(
        self,
        get_sha1,
        package_path,
        default_storage,
        mock_file,
        zipfile,
        mock_os,
        update_package_fields,
    ):
        block = self.make_one()
        mock_file_object = mock.Mock()
        mock_file_object.configure_mock(name="scorm_file_name")
        default_storage.configure_mock(size=mock.Mock(return_value="1234"))
        mock_os.configure_mock(path=mock.Mock(join=mock.Mock(return_value="path_join")))

        fields = {
            "display_name": "Test Block",
            "has_score": "True",
            "file": mock.Mock(file=mock_file_object),
            "width": None,
            "height": 450,
            "weight": 3.0,
        }

        block.studio_submit(mock.Mock(method="POST", params=fields))

        get_sha1.assert_called_once_with(mock_file_object)
        default_storage().save.assert_called_once_with(package_path, "call_file")
        mock_file.assert_called_once_with(mock_file_object)

        expected_scorm_file_meta = {
            "sha1": "sha1",
            "name": "scorm_file_name",
            "last_updated": "2018-05-01T00:00:00.000000",
            "size": block.scorm_file_meta['size'], # can't patch seek() function
        }

        self.assertEqual(block.scorm_file_meta, expected_scorm_file_meta)

        zipfile.ZipFile.assert_called_once_with(mock_file_object, "r")
        update_package_fields.assert_called_once_with()

    def test_build_file_storage_path(self):
        block = self.make_one(
            scorm_file_meta={"sha1": "sha1", "name": "scorm_file_name.html"}
        )

        file_storage_path = block.package_path

        self.assertEqual(file_storage_path, "org/course/block_type/block_id/sha1.html")

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