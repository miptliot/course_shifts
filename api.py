from rest_framework import views, permissions, response, status, generics
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.api.permissions import IsStaffOrOwner

from .models import CourseShiftSettings, CourseShiftGroup
from .serializers import CourseShiftSettingsSerializer, CourseShiftSerializer
from .manager import CourseShiftManager
from django.contrib.auth.models import User

class CourseShiftSettingsView(views.APIView):
    """
    Allows instructor to edit course shift settings
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
            return response.Response({})
        else:
            errors = serial_shift_settings.errors
            errors_by_key = []
            for key in errors.keys():
                if not errors[key]:
                    continue
                errors_by_key.append(u"{}:{}".format(key, ",".join(errors[key])))
            error_message = u";<br>".join(errors_by_key)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})


class CourseShiftListView(generics.ListAPIView):
    """
    Returns list of shifts for given course
    """
    serializer_class = CourseShiftSerializer

    def get_queryset(self):
        course_id = self.kwargs['course_id']
        course_key = CourseKey.from_string(course_id)
        return CourseShiftGroup.get_course_shifts(course_key)

    def list(self, request, course_id):
        queryset = self.get_queryset()
        serializer = CourseShiftSerializer(queryset, many=True)
        data = serializer.data
        return response.Response(data=data)


class CourseShiftDetailView(views.APIView):
    """
    Allows instructor to watch, to create and to delete course_shifts
    """

    def _get_shift(self, course_id, name):
        course_key = CourseKey.from_string(course_id)
        shift_manager = CourseShiftManager(course_key)
        shift = shift_manager.get_shift(name)
        if not shift:
            message = "Shift with name {} not found for {}".format(name, course_key)
            return None, response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})
        return shift, None

    def get(self, request, course_id):
        name = request.query_params.get("name")
        shift, error_response = self._get_shift(course_id, name)
        if not shift:
            return error_response
        data = CourseShiftSerializer(shift).data

        enroll_start, enroll_finish = shift.get_enrollment_limits()
        data["enroll_start"] = str(enroll_start)
        data["enroll_finish"] = str(enroll_finish)
        data["users_count"] = shift.users.count()
        return response.Response(data=data)

    def delete(self, request, course_id):
        name = request.data.get("name")
        shift, error_response = self._get_shift(course_id, name)
        if not shift:
            return error_response
        shift.delete()
        return response.Response({})

    def patch(self, request, course_id):
        name = request.data.get("name")
        shift, error_response = self._get_shift(course_id, name)
        if not shift:
            return error_response

        data = {
            "start_date": request.data.get("new_start_date"),
            "name": request.data.get("new_name"),
        }
        if not data:
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": "Nothing to change"})
        data['course_key'] = course_id
        serial = CourseShiftSerializer(shift, data=data, partial=True)

        if not serial.is_valid():
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": serial.error_dict()})
        try:
            data = serial.validated_data
            if data["start_date"]:
                shift.set_start_date(data["start_date"])
            if data["name"]:
                shift.set_name(data["name"])
        except ValueError as e:
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": e.message})
        return response.Response({})

    def post(self, request, course_id):
        data = {
            "start_date": request.data.get("start_date"),
            "name": request.data.get("name"),
            'course_key': course_id
        }
        serial = CourseShiftSerializer(data=data)
        if serial.is_valid():
            kwargs = serial.validated_data
        else:
            errors = serial.errors
            errors_dict = {}
            for key in errors.keys():
                if not errors[key]:
                    continue
                key_message = u",".join(unicode(x) for x in errors[key])
                errors_dict[key] = key_message
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": errors_dict})

        kwargs.pop('course_key')
        course_key = CourseKey.from_string(course_id)
        shift_manager = CourseShiftManager(course_key)
        try:
            shift_manager.create_shift(**kwargs)
        except Exception as e:
            error_message = e.message or str(e)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})
        return response.Response({})


class CourseShiftUserView(views.APIView):

    def post(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        shift_name = request.data.get("shift_name")
        shift_manager = CourseShiftManager(course_key)
        shift = shift_manager.get_shift(shift_name)
        if not shift:
            message = "Shift with name {} not found for {}".format(shift_name, course_key)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})

        username = request.data.get("username")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            message = "User with username {} not found".format(username)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})
        try:
            shift_manager.enroll_user(user, shift, forced=True)
        except ValueError as e:
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": e.message})
        return response.Response({})