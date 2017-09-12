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
    every user is enrolled to the one shift only
    CourseShiftMembership model is used (just like for CourseCohorts).

    Don't use this model's methods directly, they should be used by
    other models only. Direct usage can lead to the inconsistent
    state of shifts.
    """
    course_user_group = models.OneToOneField(CourseUserGroup)
    start_date = models.DateField(
        default=date_now,
        db_index=True,
        help_text="Date when this shift started"
        )

    days_shift = models.IntegerField(
        default=0,
        help_text="Days to add to the block's due"
    )

    @property
    def course_key(self):
        return self.course_user_group.course_id

    @property
    def users(self):
        return self.course_user_group.users

    @property
    def name(self):
        return self.course_user_group.name

    @classmethod
    def get_course_shifts(cls, course_key):
        """
        Returns all shifts groups for given course
        """
        if not isinstance(course_key, CourseKey):
            raise TypeError("course_key must be CourseKey, not {}".format(type(course_key)))
        return cls.objects.filter(course_user_group__course_id=course_key).order_by('-start_date')

    @classmethod
    def create(cls, name, course_key, start_date=None, days_shift=None):
        """
        Creates new CourseShiftGroup.
        If shift with (name, course_key) combination already exists returns this shift
        """
        course_user_group, created = CourseUserGroup.create(name=name, course_id=course_key)
        kwargs = {"course_user_group": course_user_group}
        if start_date:
            kwargs["start_date"] = start_date
        if days_shift:
            kwargs["days_shift"] = days_shift
        course_shift_group, created_shift = CourseShiftGroup.objects.get_or_create(**kwargs)
        return course_shift_group, created and created_shift

    def validate_unique(self, *args, **kwargs):
        """
        Checks that course_key and date combination is unique.
        Can't be set is constraint because course_key is taken
        from ForeignKey
        """
        val = super(CourseShiftGroup, self).validate_unique(*args, **kwargs)
        if not self.pk:
            current_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
            already_have_such_date = any([x.start_date == self.start_date for x in current_shifts])
            if already_have_such_date:
                raise ValidationError(
                    "Shift for course {} with date {} already exists".format(
                        str(self.course_key), str(self.start_date)
                    )
                )
        return val

    def __unicode__(self):
        return u"'{}' in '{}'".format(self.name, str(self.course_key))

    def delete(self, *args, **kwargs):
        group = self.course_user_group
        delete = super(CourseShiftGroup, self).delete(*args, **kwargs)
        group.delete()
        return delete

    def save(self, *args, **kwargs):
        self.validate_unique()
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
        all_memberships = cls.objects.filter(user=user)
        course_membership = all_memberships.filter(course_shift_group__course_user_group__course_id=course_key)
        membership = course_membership.first()
        if membership:
            return membership

    @classmethod
    def transfer_user(cls, user, course_shift_group_from, course_shift_group_to):
        """
        Transfers user from one shift to another one. If the first one is None,
        user is enrolled to the 'course_shift_group_to'. If the last one
        is None, user is unenrolled from shift 'course_shift_group_from'
        """

        if not course_shift_group_to and not course_shift_group_from:
            return

        if course_shift_group_from == course_shift_group_to:
            return

        key = lambda x: x.course_key if hasattr(x, "course_key") else None

        key_from = key(course_shift_group_from)
        key_to = key(course_shift_group_to)
        if course_shift_group_from and course_shift_group_to:
            if str(key_from) != str(key_to):
                raise ValueError("Course groups have different course_key's: {} and {}".format(
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
        Adds user to CourseShiftGroup if he has membership for this group or None.
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
        save = super(CourseShiftGroupMembership, self).save(*args, **kwargs)
        if self.user not in self.course_shift_group.users.all():
            self._push_add_to_group(self.course_shift_group, self.user)
        return save

    def delete(self, *args, **kwargs):
        delete = super(CourseShiftGroupMembership, self).delete(*args, **kwargs)
        self._push_delete_from_group(self.user, self.course_shift_group)
        return delete

    def __unicode__(self):
        return u"'{}' in '{}'".format(
            self.user.username,
            self.course_shift_group.name
        )


class CourseShiftSettings(models.Model):
    """
    Describes how should course shifts be run for
    course session.
    """
    course_key = CourseKeyField(
        max_length=255,
        db_index=True,
        unique=True,
        )

    is_shift_enabled = models.BooleanField(
        default=False,
        help_text="Is feature enabled for course"
    )

    is_autostart = models.BooleanField(
        default=True,
        help_text="Are groups generated automatically with period "
                  "or according to the manually set plan")

    autostart_period_days = models.IntegerField(
        default=28,
        db_column='autostart_period_days',
        help_text="Period of generated groups",
        null=True
        )

    enroll_before_days = models.IntegerField(
        default=14,
        help_text="Days before start when student can enroll already"
    )

    enroll_after_days = models.IntegerField(
        default=7,
        help_text="Days after start when student still can enroll"
    )

    @property
    def last_start_date(self):
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
        return current_settings

    def update_shifts(self):
        plan = self.get_next_plan()
        is_updated = False
        while plan:
            is_updated = True
            name = self._naming(self.course_key, plan.start_date)
            days_add = int((plan.start_date - self.course_start_date).days)
            plan.launch_shift(name=name, days_add=days_add)
            plan = self.get_next_plan()
        return is_updated

    def get_next_plan(self):
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
        return "shift_{}_{}".format(str(course_key), str(date))

    def create_plan(self, start_date):
        created, plan = CourseShiftPlannedRun.objects.get_or_create(
            course_shift_settings=self,
            start_date=start_date,
        )
        return plan


class CourseShiftPlannedRun(models.Model):
    """
    Represents planned shift for course. Real plans are stored
    in db and user only when new shifts are generated manually('is_autostart'=False)
    Also used as a mock for autostart to keep same syntax
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
        but doesn't hit database in any way
        """
        mock = cls(course_shift_settings=settings, start_date=start_date)
        setattr(mock, cls.MOCKING_FLAG, True)
        mock.delete = lambda: None
        mock.save = lambda: None
        return mock

    @classmethod
    def clear_course_shift_plans(cls, course_key):
        plans = cls.objects.filter(course_shift_settings__course_key=course_key)
        for x in plans:
            x.delete()

    @classmethod
    def get_course_plans(cls, course_key):
        return cls.objects.filter(course_shift_settings__course_key=course_key)

    def launch_shift(self, name, days_add):
        """
        Launches shift according to plan and self-destructs
        """
        shift, created = CourseShiftGroup.create(
            course_key=self.course_shift_settings.course_key,
            name=name,
            days_shift=days_add,
            start_date=self.start_date
        )
        self.delete()
        return shift

    def __unicode__(self):
        return u"{} for {}".format(str(self.start_date), str(self.course_shift_settings.course_key))
