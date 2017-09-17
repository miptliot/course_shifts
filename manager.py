from datetime import timedelta
from logging import getLogger

from django.utils import timezone
from models import CourseShiftGroup, CourseShiftGroupMembership, CourseShiftSettings


date_now = lambda: timezone.now().date()
log = getLogger(__name__)


class CourseShiftManager(object):
    """
    Provides the interface to perform operations on users and
    course shifts: user transfer between shifts, due date calculation,
    active shifts etc.
    """

    def __init__(self, course_key):
        self.course_key = course_key
        self.settings = CourseShiftSettings.get_course_settings(self.course_key)

    @property
    def is_shift_enabled(self):
        return self.settings.is_shift_enabled

    def get_user_shift(self, user, course_key):
        """
        Returns user's shift group for given course.
        """
        if not self.settings.is_shift_enabled:
            return

        membership = CourseShiftGroupMembership.get_user_membership(user, course_key)
        if membership:
            return membership.course_shift_group

    def get_all_shifts(self):
        return CourseShiftGroup.get_course_shifts(self.course_key)

    def get_active_shifts(self, user=None):
        """
        Returns shifts that are are active at this moment according to the settings,
        i.e. enrollment have started but haven't finished yet.
        If user is given and he has membership all started shifts are considered
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
            current_group = self.get_user_shift(user, self.course_key)
            current_start_date = current_group and current_group.start_date

        for shift in all_shifts:
            enroll_start = shift.start_date - timedelta(days=self.settings.enroll_before_days)
            enroll_finish = shift.start_date + timedelta(days=self.settings.enroll_after_days)
            if current_start_date and current_start_date < shift.start_date:
                enroll_finish = now

            if enroll_start < now <= enroll_finish:
                active_shifts.append(shift)

        return active_shifts

    def sign_user_on_shift(self, user, shift, course_key):
        """
        Transfers user to given shift group. User's enrollment is not checked
        because at course enrollment user should be firstly transfered to shift and
        only then enrolled on course.
        :param user: user to enroll on shift
        :param shift: CourseShiftGroup to enroll
        :param course_key: to which course shift_to (and shift_from if not None) belongs
        """
        if shift.course_key != course_key:
            raise ValueError("Shift's course_key: '{}', given course_key:'{}'".format(
                str(shift.course_key),
                str(course_key)
            ))

        membership = CourseShiftGroupMembership.get_user_membership(user=user, course_key=course_key)
        shift_from = membership and membership.course_shift_group
        if shift_from == shift:
            return membership

        active_shifts = self.get_active_shifts(user)
        if shift not in active_shifts:
            raise ValueError("Shift {} is not in active shifts: {}".format(
                str(shift),
                str(active_shifts)
            ))

        return CourseShiftGroupMembership.transfer_user(user, shift_from, shift)

    def create_shift(self, start_date):
        """
        Creates plan with given start date.
        """
        if not self.settings.is_shift_enabled:
            return ValueError("Can't create shift: feature is turned off for course")
        if self.settings.is_autostart:
            raise ValueError("Can't create shift in autostart mode")

        name = self.settings.build_name(start_date)
        days_shift = self.settings.calculate_days_add(start_date)
        shift, created = CourseShiftGroup.create(
            name=name,
            course_key=self.course_key,
            start_date=start_date,
            days_shift=days_shift
        )
        return shift