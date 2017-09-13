from datetime import timedelta
from logging import getLogger

from django.utils import timezone
from models import CourseShiftGroup, CourseShiftGroupMembership, CourseShiftSettings


date_now = lambda: timezone.now().date()
log = getLogger(__name__)


class CourseShiftUserManager(object):
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

    def get_user_course_shift(self, user, course_key):
        """
        Returns user's shift group for given course.
        """
        if not self.settings.is_shift_enabled:
            return

        membership = CourseShiftGroupMembership.get_user_membership(user, course_key)
        if membership:
            return membership.course_shift_group

    def get_active_shifts(self, date_threshold=None):
        """
        Returns shifts that are are active at this moment according to the settings.
        date_threshold add additional filter for shifts start date against threshold
        (e.g. for user switching shift to the newer shift)
        """
        if not self.settings.is_shift_enabled:
            return []
        current_date = date_now()
        all_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        if not all_shifts:
            return []

        active_shifts = []
        for shift in all_shifts:
            enroll_finish = shift.start_date + timedelta(days=self.settings.enroll_after_days)
            enroll_start = shift.start_date - timedelta(days=self.settings.enroll_before_days)
            if not(enroll_start < current_date < enroll_finish):
                continue
            if date_threshold and shift.start_date < date_threshold:
                continue
            active_shifts.append(shift)
        return active_shifts

    def sign_user_on_shift(self, user, shift_to, course_key, shift_from=None, forced=False, shift_up_only=True):
        """
        Transfers user to given shift group. User's enrollment is not checked
        because at course enrollment user should be firstly transfered to shift and
        only then enrolled on course.
        If forced, then user unenrolled from current course shift automatically,
        otherwise user mustn't have any current shift membership
        :param user: user to enroll on shift
        :param shift_to: CourseShiftGroup to enroll
        :param course_key: to which course shift_to (and shif_from if not None) belongs
        :param forced: unenroll from current shift if shift_from is not given
        :param shift_up_only: allow to change only on later shifts
        """
        if shift_to.course_key != course_key:
            raise ValueError("Shift's course_key: '{}', given course_key:'{}'".format(
                str(shift_to.course_key),
                str(course_key)
            ))
        if shift_from and shift_from.course_key != course_key:
            raise ValueError("Shift_from's  course_key: '{}', given course_key:'{}'".format(
                str(shift_from.course_key),
                str(course_key)
            ))

        membership = CourseShiftGroupMembership.get_user_membership(user=user, course_key=course_key)
        group_from = membership and membership.course_shift_group
        if group_from == shift_to:
            return membership

        if not forced and group_from != shift_from:
            raise ValueError("User's membership for given course is not None:{}".format(str(membership)))

        date_threshold = shift_from and shift_from.start_date
        if not shift_up_only:
            date_threshold = None

        active_shifts = self.get_active_shifts(date_threshold=date_threshold)
        if shift_to not in active_shifts:
            raise ValueError("Shift {} is not in active shifts: {}".format(
                str(shift_to),
                str(active_shifts)
            ))

        return CourseShiftGroupMembership.transfer_user(user, group_from, shift_to)

