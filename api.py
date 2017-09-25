from rest_framework import views, permissions, response, status, generics
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.api.permissions import IsStaffOrOwner

from .models import CourseShiftSettings, CourseShiftGroup
from .serializers import CourseShiftSettingsSerializer, CourseShiftSerializer


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
        data = dict(request.data.iteritems())
        data = dict((x,str(data[x])) for x in data)
        data['course_key'] = course_id
        serial_shift_settings = CourseShiftSettingsSerializer(data=data, partial=True)
        if serial_shift_settings.is_valid():
            course_key = serial_shift_settings.validated_data['course_key']
            instance = CourseShiftSettings.get_course_settings(course_key)
            serial_shift_settings.update(instance, serial_shift_settings.validated_data)
            return response.Response()
        else:
            errors = serial_shift_settings.errors
            errors_by_key = []
            for key in errors.keys():
                if not errors[key]:
                    continue
                errors_by_key.append(u"{}:{}".format(key, ",".join(errors[key])))
            error_message = u";<br>".join(errors_by_key)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})

