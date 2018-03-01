from django.contrib.auth.models import User
from opaque_keys.edx.keys import CourseKey
from openedx.core.lib.api.permissions import IsStaffOrOwner, ApiKeyHeaderPermission
from rest_framework import views, permissions, response, status, generics

from .manager import CourseShiftManager
from .serializers import CourseShiftSettingsSerializer, CourseShiftSerializer


class CourseShiftsPermission(permissions.BasePermission):
    """
    Allows staff or api-key users to change shifts.
    """
    def has_permission(self, request, view):
        return (ApiKeyHeaderPermission().has_permission(request, view) or
            (permissions.IsAuthenticated().has_permission(request, view) and IsStaffOrOwner().has_permission(request,view))
        )


class CourseShiftSettingsView(views.APIView):
    """
    Allows instructor to edit course shift settings
    """
    permission_classes = CourseShiftsPermission,

    def get(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        manager = CourseShiftManager(course_key)
        shift_settings = manager.settings
        if shift_settings.is_shift_enabled:
            serial_shift_settings = CourseShiftSettingsSerializer(shift_settings)
            data = serial_shift_settings.data
            data.pop('course_key')
            return response.Response(data=data)
        else:
            return response.Response({})

    def post(self, request, course_id):
        data = dict(request.data.iteritems())
        data = dict((x, str(data[x])) for x in data)
        course_key = CourseKey.from_string(course_id)
        manager = CourseShiftManager(course_key)
        errors = manager.update_settings(data)
        if not errors:
            return response.Response({})
        else:
            error_message = u";<br>".join(errors)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": error_message})


class CourseShiftListView(generics.ListAPIView):
    """
    Returns list of shifts for given course
    """
    serializer_class = CourseShiftSerializer
    permission_classes = CourseShiftsPermission,

    def old_get_queryset(self):
        course_id = self.kwargs['course_id']
        course_key = CourseKey.from_string(course_id)
        manager = CourseShiftManager(course_key)
        return manager.get_all_shifts()

    def list(self, request, course_id):
        course_id = self.kwargs['course_id']
        course_key = CourseKey.from_string(course_id)
        shift_manager = CourseShiftManager(course_key)
        username = request.query_params.get('username', None)
        if username:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                message = "User with username {} not found".format(username)
                return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})
            queryset = shift_manager.get_active_shifts(user)
        else:
            queryset = shift_manager.get_all_shifts()
        serializer = CourseShiftSerializer(queryset, many=True)
        data = serializer.data
        return response.Response(data=data)


class CourseShiftDetailView(views.APIView):
    """
    Allows instructor to watch, to create, to modify and to delete course shifts
    """
    permission_classes = CourseShiftsPermission,

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
            if data["name"] != shift.name:
                message = "Shift name can't be changed. You can delete shift and create new one."
                return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})

            if data["start_date"] != shift.start_date:
                shift.set_start_date(data["start_date"])
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
    """
    Allows instructor to add users to shifts and check their
    current shift
    """
    permission_classes = CourseShiftsPermission,

    def post(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        shift_manager = CourseShiftManager(course_key)
        if not shift_manager.is_enabled:
            message = "Shifts are not enabled for course {}".format(course_id)
            return response.Response(status=status.HTTP_406_NOT_ACCEPTABLE, data={"error": message})

        username = request.data.get("username")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            message = "User with username {} not found".format(username)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})

        shift_name = request.data.get("shift_name")
        shift = shift_manager.get_shift(shift_name)
        if not shift:
            message = "Shift with name {} not found for {}".format(shift_name, course_id)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})

        try:
            shift_manager.enroll_user(user, shift, forced=True)
        except ValueError as e:
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": e.message})
        return response.Response({"message": "Success"})

    def get(self, request, course_id):
        course_key = CourseKey.from_string(course_id)
        shift_manager = CourseShiftManager(course_key)
        if not shift_manager.is_enabled:
            message = "Shifts are not enabled for course {}".format(course_id)
            return response.Response(status=status.HTTP_406_NOT_ACCEPTABLE, data={"error": message})

        username = request.query_params.get("username")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            message = "User with username {} not found".format(username)
            return response.Response(status=status.HTTP_400_BAD_REQUEST, data={"error": message})
        current_shift = shift_manager.get_user_shift(user)
        if not current_shift:
            return response.Response({})
        else:
            data = CourseShiftSerializer(current_shift).data
            return response.Response(data)
