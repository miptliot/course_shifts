from datetime import timedelta

from django.utils import timezone
from models import CourseShiftGroup, CourseShiftGroupMembership, CourseShiftSettings


date_now = lambda: timezone.now().date()


class CourseShiftManager(object):
    """
    Provides the interface to perform operations on users and
    shifts for given course: user transfer between shifts, shift creation,
    data about available shifts. Supposed to be used outside the app in edx
    """

    def __init__(self, course_key):
        self.course_key = course_key
        self.settings = CourseShiftSettings.get_course_settings(self.course_key)

    @property
    def is_enabled(self):
        return self.settings.is_shift_enabled

    def get_user_shift(self, user):
        """
        Returns user's shift group for manager's course.
        """
        if not self.settings.is_shift_enabled:
            return

        membership = CourseShiftGroupMembership.get_user_membership(user, self.course_key)
        if membership:
            return membership.course_shift_group

    def get_all_shifts(self):
        return CourseShiftGroup.get_course_shifts(self.course_key)

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

        now = date_now()
        active_shifts = []
        current_start_date = None
        if user:
            current_shift = self.get_user_shift(user)
            current_start_date = current_shift and current_shift.start_date

        for shift in all_shifts:
            enroll_start = shift.start_date - timedelta(days=self.settings.enroll_before_days)
            enroll_finish = shift.start_date + timedelta(days=self.settings.enroll_after_days)
            if current_start_date and current_start_date < shift.start_date:
                # If user is in group 'current_shift,' which is older than given 'shift',
                # then all groups later than 'current' are available for user.
                # This means that enroll_finish for this shift should be ignored.
                # Because later enroll_finish is compared with 'now', it is replaced
                # by 'now' to pass the check successfully anyway
                enroll_finish = now
            if enroll_start < now <= enroll_finish:
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
