"""
This file contains the logic for course shifts.
"""
from datetime import timedelta
from logging import getLogger

from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models, IntegrityError
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.django import modulestore

from openedx.core.djangoapps.course_groups.models import CourseUserGroup, CourseKeyField

log = getLogger(__name__)


def date_now():
    return timezone.now().date()


class CourseShiftGroup(models.Model):
    """
    Represents group of users with shifted due dates.
    It is based on CourseUserGroup. To ensure that
    every user is enrolled in the one shift only
    CourseShiftMembership model is used (just like for CourseCohorts).

    Don't use this model's methods directly, they should be used by
    other models only. Direct usage can lead to the inconsistent
    state of shifts.
    """
    course_user_group = models.OneToOneField(CourseUserGroup)
    course_key = CourseKeyField(
        max_length=255,
        db_index=True,
        help_text="Which course is this group associated with")
    start_date = models.DateField(
        default=date_now,
        help_text="Date when this shift starts"
        )
    days_shift = models.IntegerField(
        default=0,
        help_text="Days to add to the block's due"
    )

    class Meta:
        unique_together = ('course_key', 'start_date',)

    @property
    def users(self):
        return self.course_user_group.users

    @property
    def name(self):
        return self.course_user_group.name

    def get_shifted_due(self, user, block, name):
        value = getattr(block, name)
        if not value:
            return
        if user not in self.users.all():
            raise ValueError("User '{}' is not in shift '{}'".format(
                user.username,
                str(self)
            ))
        return value + timedelta(days=self.days_shift)

    @classmethod
    def get_course_shifts(cls, course_key):
        """
        Returns all shifts groups for given course
        """
        if not isinstance(course_key, CourseKey):
            raise TypeError("course_key must be CourseKey, not {}".format(type(course_key)))
        return cls.objects.filter(course_key=course_key).order_by('-start_date')

    @classmethod
    def create(cls, name, course_key, start_date=None, days_shift=None):
        """
        Creates new CourseShiftGroup.
        If shift with (name, course_key) combination already exists returns this shift
        """
        course_user_group, created_group = CourseUserGroup.create(name=name, course_id=course_key)
        kwargs = {"course_user_group": course_user_group}
        if start_date:
            kwargs["start_date"] = start_date
        if days_shift:
            kwargs["days_shift"] = days_shift
        kwargs['course_key'] = course_key
        course_shift_group, created_shift = CourseShiftGroup.objects.get_or_create(**kwargs)
        is_created = created_group and created_shift
        return course_shift_group, is_created

    def __unicode__(self):
        return u"'{}' in '{}'".format(self.name, str(self.course_key))

    def delete(self, *args, **kwargs):
        log.info("Shift group is deleted: {}".format(str(self)))
        self.course_user_group.delete()
        return super(CourseShiftGroup, self).delete(*args, **kwargs)

    def save(self, *args, **kwargs):
        if self.course_key != self.course_user_group.course_id:
            raise ValidationError("Different course keys in shift and user group: '{}' and '{}'".format(
                str(self.course_key),
                str(self.course_user_group.course_id)
            ))
        if not self.pk:
            log.info("New shift group is created: '{}'".format(str(self)))
        return super(CourseShiftGroup, self).save(*args, **kwargs)


class CourseShiftGroupMembership(models.Model):
    """
    Represents membership in CourseShiftGroup. At any changes it
    updates CourseUserGroup.
    """
    user = models.ForeignKey(User, related_name="shift_membership")
    course_shift_group = models.ForeignKey(CourseShiftGroup)

    @property
    def course_key(self):
        return self.course_shift_group.course_key

    @classmethod
    def get_user_membership(cls, user, course_key):
        """
        Returns CourseUserGroup for user and course if membership exists, else None
        """
        if not course_key:
            raise ValueError("Got course_key {}".format(str(course_key)))
        try:
            course_membership = cls.objects.get(user=user, course_shift_group__course_key=course_key)
        except cls.DoesNotExist:
            course_membership = None
        return course_membership

    @classmethod
    def transfer_user(cls, user, course_shift_group_from, course_shift_group_to):
        """
        Transfers user from one shift to another one. If the first one is None,
        user is enrolled in the 'course_shift_group_to'. If the last one
        is None, user is unenrolled from shift 'course_shift_group_from'
        """

        if not course_shift_group_to and not course_shift_group_from:
            return

        if course_shift_group_from == course_shift_group_to:
            return

        key_from = course_shift_group_from and course_shift_group_from.course_key
        key_to = course_shift_group_to and course_shift_group_to.course_key

        if course_shift_group_from and course_shift_group_to:
            if str(key_from) != str(key_to):
                raise ValueError("Course groups have different course_key's: '{}' and '{}'".format(
                    str(key_from), str(key_to)
                    )
                )
        current_course_key = key_from or key_to
        membership = cls.get_user_membership(user, current_course_key)
        membership_group = membership and membership.course_shift_group

        if membership_group != course_shift_group_from:
            raise ValueError("User's membership is '{}', not '{}'".format(
                str(membership_group),
                str(course_shift_group_from)
                )
            )
        if membership:
            membership.delete()
        if course_shift_group_to:
            return cls.objects.create(user=user, course_shift_group=course_shift_group_to)

    @classmethod
    def _push_add_to_group(cls, course_shift_group, user):
        """
        Adds user to CourseShiftGroup if he has membership for this group or doesn't have membership.
        """
        membership = CourseShiftGroupMembership.get_user_membership(user=user, course_key=course_shift_group.course_key)
        membership_group = membership and membership.course_shift_group

        if membership_group and membership_group != course_shift_group:
            raise IntegrityError("Found membership for user {}, supposed to be {} or None".format(
                membership_group,
                course_shift_group.name
            ))

        if user not in course_shift_group.users.all():
            course_shift_group.course_user_group.users.add(user)

    @classmethod
    def _push_delete_from_group(cls, user, course_shift_group):
        """
        Deletes user from course_shift_group if he doesn't have membership.
        """
        membership = CourseShiftGroupMembership.get_user_membership(user=user, course_key=course_shift_group.course_key)
        membership_group = membership and membership.course_shift_group

        if membership_group:
            raise IntegrityError("Found membership for user {}, supposed to be None".format(
                user.username,
                membership_group.name
            ))
        if user not in course_shift_group.course_user_group.users.all():
            raise IntegrityError("User {} is not in {}".format(user.username, course_shift_group.name))
        course_shift_group.course_user_group.users.remove(user)

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError("CourseShiftGroupMembership can't be changed, only deleted")
        current_membership = self.get_user_membership(self.user, self.course_key)
        if current_membership:
            raise ValueError("User already has membership for this course: {}".format(
                str(current_membership)
            ))
        save_result = super(CourseShiftGroupMembership, self).save(*args, **kwargs)
        log.info("User '{}' is enrolled in shift '{}'".format(
            self.user.username,
            str(self.course_shift_group))
        )
        if self.user not in self.course_shift_group.users.all():
            self._push_add_to_group(self.course_shift_group, self.user)
        return save_result

    def delete(self, *args, **kwargs):
        log.info("User '{}' is unenrolled from shift '{}'".format(
            self.user.username,
            str(self.course_shift_group))
        )
        super(CourseShiftGroupMembership, self).delete(*args, **kwargs)
        self._push_delete_from_group(self.user, self.course_shift_group)

    def __unicode__(self):
        return u"'{}' in '{}'".format(
            self.user.username,
            self.course_shift_group.name
        )


class CourseShiftSettings(models.Model):
    """
    Describes Course Shift settings for start and due dates in the specific course run.
    """
    course_key = CourseKeyField(
        max_length=255,
        db_index=True,
        unique=True,
    )

    is_shift_enabled = models.BooleanField(
        default=False,
        help_text="True value if this feature is enabled for the course run"
    )

    is_autostart = models.BooleanField(
        default=True,
        help_text="Are groups generated automatically with period "
                  "or according to the manually set plan")

    autostart_period_days = models.IntegerField(
        default=28,
        db_column='autostart_period_days',
        help_text="Number of days between new automatically generated shifts."\
            "Used only in autostart mode.",
        null=True
        )

    enroll_before_days = models.IntegerField(
        default=14,
        help_text="Days before shift start when student can enroll already."\
        "E.g. if shift starts at 01/20/2020 and value is 5 then shift will be"\
        "available from 01/15/2020."
    )

    enroll_after_days = models.IntegerField(
        default=7,
        help_text="Days after shift start when student still can enroll." \
        "E.g. if shift starts at 01/20/2020 and value is 10 then shift will be" \
        "available till 01/20/2020"
    )

    @property
    def last_start_date(self):
        """
        Date when the last shift was started.
        """
        shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        if not shifts:
            return self.course_start_date
        return shifts[0].start_date

    @property
    def course_start_date(self):
        course = modulestore().get_course(self.course_key)
        return course.start.date()

    @classmethod
    def get_course_settings(cls, course_key):
        current_settings, created = cls.objects.get_or_create(course_key=course_key)
        if created:
            log.info("Settings for {} are created".format(
                str(course_key)
            ))
        return current_settings

    def update_shifts(self):
        """
        Checks current date and creates new shifts if necessary
        according to the settings
        :return: if new shifts were created
        """
        plan = self.get_next_plan()
        is_updated = False
        while plan:
            is_updated = True
            name = self._naming(self.course_key, plan.start_date)
            days_add = int((plan.start_date - self.course_start_date).days)
            plan.launch_shift(name=name, days_add=days_add)
            plan = self.get_next_plan()
        if is_updated:
            log.info(
                "Shifts for course '{}' are updated".format(str(self.course_key))
            )
        return is_updated

    def create_plan(self, start_date, launch_plan=False):
        """
        Creates plan with given start date.
        There is no check that shift are in manual mode
        """
        created, plan = CourseShiftPlannedRun.objects.get_or_create(
            course_shift_settings=self,
            start_date=start_date,
        )
        return plan

    def get_next_plan(self):
        """
        Returns closest CourseShiftPlannedRun or None if
        feature is turned off or no plans available currently
        """
        if not self.is_shift_enabled:
            return None
        if self.is_autostart:
            plan = self._get_next_autostart_plan()
        else:
            plan = self._get_next_manual_plan()
        return plan

    def _get_next_autostart_plan(self):
        last_date = self.last_start_date
        next_start_date = last_date + timedelta(days=self.autostart_period_days)
        now_time = date_now()
        if next_start_date > now_time:
            return None
        return CourseShiftPlannedRun.get_mocked_plan(self, next_start_date)

    def _get_next_manual_plan(self):
        course_shifts_plans = self.plans.all().order_by('start_date')
        if not course_shifts_plans:
            return False
        return course_shifts_plans.first()

    @classmethod
    def _naming(cls, course_key, date):
        """
        Defines how should be shifts named
        """
        return "shift_{}_{}".format(str(course_key), str(date))


class CourseShiftPlannedRun(models.Model):
    """
    Represents planned shift for course.
    Plan can be launched, then it creates the shift and disappears.
    For 'autostart' mode in settings mocked plans can be created:
    they can be launched, but they are not stored in db and don't hit
    it at plan deletion.
    """
    course_shift_settings = models.ForeignKey(
        CourseShiftSettings,
        related_name="plans")
    start_date = models.DateField(default=timezone.now)

    class Meta:
        unique_together = ('course_shift_settings', 'start_date',)

    MOCKING_FLAG = "mocking_flag"

    @classmethod
    def get_mocked_plan(cls, settings, start_date):
        """
        Returns mocked plan for autostart mode. It can be launched,
        but doesn't hit database at deletion
        """
        mock = cls(course_shift_settings=settings, start_date=start_date)
        setattr(mock, cls.MOCKING_FLAG, True)
        mock.delete = lambda: None
        mock.save = lambda: None
        return mock

    @classmethod
    def get_course_plans(cls, course_key):
        return cls.objects.filter(course_shift_settings__course_key=course_key)

    def launch_shift(self, name, days_add):
        """
        Launches shift according to plan and then self-destructs
        """

        shift, created = CourseShiftGroup.create(
            course_key=self.course_shift_settings.course_key,
            name=name,
            days_shift=days_add,
            start_date=self.start_date
        )
        log.info(
            "Shift plan {} is launched as shift {}".format(
                str(self),
                str(shift)
            )
        )
        self.delete()
        return shift

    def __unicode__(self):
        return u"{} for {}".format(str(self.start_date), str(self.course_shift_settings.course_key))
