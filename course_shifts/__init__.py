from django.core.urlresolvers import reverse
from django.utils.translation import ugettext as _

from .models import CourseShiftSettings
from .serializers import CourseShiftSettingsSerializer, CourseShiftSerializer
from .manager import CourseShiftManager


def _section_course_shifts(course, access):
    course_key = course.id
    course_id = str(course_key)
    url_settings = reverse('course_shifts:settings', kwargs={"course_id":course_id})
    url_list = reverse('course_shifts:list', kwargs={"course_id": course_id})
    url_detail = reverse('course_shifts:detail', kwargs={"course_id": course_id})
    url_membership = reverse('course_shifts:membership', kwargs={"course_id": course_id})

    shift_manager = CourseShiftManager(course_key)
    if not shift_manager.is_enabled:
        return {}
    serial_settings = shift_manager.get_serial_settings()
    section_data = {
        'section_key': 'course_shifts',
        'section_display_name': _('Course Shifts'),
        'access': access,
        'course_shifts_settings_url': url_settings,
        'course_shifts_list_url': url_list,
        'course_shifts_detail_url': url_detail,
        'course_shifts_membership_url':url_membership,
        'current_settings': serial_settings.data,
    }
    return section_data


def get_course_active_shifts_json(course_key):
    shift_manager = CourseShiftManager(course_key)
    active_shifts = shift_manager.get_active_shifts()
    serializer = CourseShiftSerializer(active_shifts, many=True)
    return serializer.data
