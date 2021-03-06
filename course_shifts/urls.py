"""
URLs for course shifts app
"""
from django.conf import settings
from django.conf.urls import patterns, url

from .api import CourseShiftSettingsView, CourseShiftListView, CourseShiftDetailView, CourseShiftUserView

urlpatterns = patterns(
    'course_shifts',
    url(r'^detail/{}/$'.format(settings.COURSE_ID_PATTERN), CourseShiftDetailView.as_view(),
        name='detail'),
    url(r'^membership/{}$'.format(settings.COURSE_ID_PATTERN), CourseShiftUserView.as_view(),
        name='membership'),
    url(r'^settings/{}/$'.format(settings.COURSE_ID_PATTERN), CourseShiftSettingsView.as_view(),
        name='settings'),
    url(r'^{}/$'.format(settings.COURSE_ID_PATTERN), CourseShiftListView.as_view(),
        name='list'),

)
