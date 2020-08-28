#!/bin/dash

pip install -e /openedx/requirements/edx_xblock_scorm

cd /openedx/requirements/edx_xblock_scorm/scormxblock
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/edx_xblock_scorm/scormxblock

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest tests.py

rm -rf test_root