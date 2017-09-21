from rest_framework import views, permissions, response, status
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.api.permissions import IsStaffOrOwner

from .models import CourseShiftSettings
from .serializers import CourseShiftSettingsSerializer


class CourseShiftSettingsView(views.APIView):
    """
    Allows instructor to manipulate course shift settings
    """
    #permission_classes = (permissions.IsAuthenticated, IsStaffOrOwner)
    permissions = tuple()

    def get(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        shift_settings = CourseShiftSettings.get_course_settings(course_key)
        serial_shift_settings = CourseShiftSettingsSerializer(shift_settings)
        data = serial_shift_settings.data
        data.pop('course_key')
        return response.Response(data=data)

    def post(self, request, course_id):
        data = request.data
        data['course_key'] = course_id
        serial_shift_settings = CourseShiftSettingsSerializer(data=data)
        if serial_shift_settings.is_valid():
            course_key = serial_shift_settings.validated_data['course_key']
            instance = CourseShiftSettings.get_course_settings(course_key)
            serial_shift_settings.update(instance, serial_shift_settings.validated_data)
            return response.Response()
        else:
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data=serial_shift_settings.errors)
