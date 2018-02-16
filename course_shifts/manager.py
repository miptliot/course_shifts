from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from .models import CourseShiftGroup, CourseShiftGroupMembership, CourseShiftSettings
from .serializers import CourseShiftSettingsSerializer

date_now = lambda: timezone.now().date()


class CourseShiftManager(object):
    """
    Provides the interface to perform operations on users and
    shifts for given course: user transfer between shifts, shift creation,
    data about available shifts. Supposed to be used outside the app in edx
    """
    SHIFT_COURSE_FIELD_NAME = "enable_course_shifts"
    SETTINGS_CACHE = {
        "key":'CourseShiftSettings_{course_id}',
        "timeout": 300
    }
    MEMBERSHIP_CACHE = {
        "key": 'CourseShiftGroupMembership_{course_id}_{username}',
        "timeout": 300
    }

    def __init__(self, course_key):
        self.course_key = course_key

    @property
    def settings(self):
        if hasattr(self, '_settings'):
            return self._settings
        cache_key = self.SETTINGS_CACHE['key'].format(course_id=str(self.course_key))
        cached_settings = cache.get(cache_key)
        if cached_settings:
            self._settings = cached_settings
            return cached_settings

        self._settings = CourseShiftSettings.get_course_settings(self.course_key)
        cache.set(cache_key, self._settings, self.SETTINGS_CACHE['timeout'])
        return self._settings

    @property
    def is_enabled(self):
        course = self.settings.course
        if self.settings.is_shift_enabled:
            return True
        field = self.SHIFT_COURSE_FIELD_NAME
        if hasattr(course, field) and getattr(course, field):
            self.settings.is_shift_enabled = True
            self.settings.save()
            return True
        return False

    def get_user_shift(self, user):
        """
        Returns user's shift group for manager's course.
        """
        if not self.is_enabled:
            return

        cache_key = self.MEMBERSHIP_CACHE['key'].format(
            course_id=str(self.course_key),
            username=user.username
        )
        cached_membership = cache.get(cache_key)
        if cached_membership:
            if isinstance(cached_membership, str):
                # next is always True, left for readability
                if cached_membership == 'None':
                    return None
            return cached_membership.course_shift_group

        membership = CourseShiftGroupMembership.get_user_membership(user, self.course_key) or 'None'
        cache.set(cache_key, membership, self.MEMBERSHIP_CACHE['timeout'])
        return getattr(membership, 'course_shift_group', None)

    def get_all_shifts(self):
        return CourseShiftGroup.get_course_shifts(self.course_key)

    def get_shift(self, name):
        shift = CourseShiftGroup.get_shift(course_key=self.course_key, name=name)
        if shift:
            shift.settings = self.settings
        return shift

    def get_active_shifts(self, user=None):
        """
        Returns shifts that are are active at this moment according to the settings,
        i.e. enrollment have started but haven't finished yet.
        If user is given and he has membership all later started shifts are considered
        as active
        """
        if not self.settings.is_shift_enabled:
            return []
        all_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        if not all_shifts:
            return []

        active_shifts = []
        current_start_date = None
        if user:
            current_shift = self.get_user_shift(user)
            current_start_date = current_shift and current_shift.start_date

        for shift in all_shifts:
            # There are 2 cases when shift is active:
            # 1. Shift is enrollable now
            # 2. All together are true:
            #    a. User has current_shift
            #    b. current_shift older than shift
            #    c. shift has already started

            shift_is_enrollable = shift.is_enrollable_now()
            shift_is_old_for_user = current_start_date and current_start_date <= shift.start_date and shift.is_started()
            if shift_is_enrollable or shift_is_old_for_user:
                active_shifts.append(shift)

        return active_shifts

    def enroll_user(self, user, shift, forced=False):
        """
        Enrolls user on given shift. If user is enrolled on other shift,
        his current shift membership canceled. If shift is None only current membership
        is canceled. Enrollment is allowed only on 'active shifts' for given user
        (watch 'get_active_shift')
        If forced is True, user can be enrolled on inactive shift.
        """
        if shift and shift.course_key != self.course_key:
            raise ValueError("Shift's course_key: '{}', manager course_key:'{}'".format(
                str(shift.course_key),
                str(self.course_key)
            ))

        membership = CourseShiftGroupMembership.get_user_membership(
            user=user,
            course_key=self.course_key
        )
        shift_from = membership and membership.course_shift_group
        if shift_from == shift:
            return membership

        user_can_be_enrolled = forced
        if not shift: # unenroll is possible at any time
            user_can_be_enrolled = True
        active_shifts = []
        if not user_can_be_enrolled:
            active_shifts = self.get_active_shifts(user)
            if shift in active_shifts:
                user_can_be_enrolled = True
        if not user_can_be_enrolled:
            raise ValueError("Shift {} is not in active shifts: {}".format(
                str(shift),
                str(active_shifts)
            ))
        return CourseShiftGroupMembership.transfer_user(user, shift_from, shift)

    def create_shift(self, start_date=None, name=None):
        """
        Creates shift with given start date and name.If start_date is not
        specified then shift created with start_date 'now'.
        If name is not specified, name is got from 'settings.build_default_name'
        """
        if not self.settings.is_shift_enabled:
            raise ValueError("Can't create shift: feature is turned off for course")
        if self.settings.is_autostart:
            raise ValueError("Can't create shift in autostart mode")
        if not start_date:
            start_date = date_now()
        if not name:
            name = self.settings.build_default_name(start_date=start_date)
        days_shift = self.settings.calculate_days_shift(start_date)
        shift, created = CourseShiftGroup.create(
            name=name,
            course_key=self.course_key,
            start_date=start_date,
            days_shift=days_shift
        )
        return shift

    def get_serial_settings(self):
        return CourseShiftSettingsSerializer(self.settings)