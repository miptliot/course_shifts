"""
URLs for course shifts app
"""
from django.conf import settings
from django.conf.urls import patterns, url

from .api import CourseShiftSettingsView

urlpatterns = patterns(
    'course_shifts',
    url(r'^settings/{}/$'.format(settings.COURSE_ID_PATTERN), CourseShiftSettingsView.as_view(), name='settings'),
)
