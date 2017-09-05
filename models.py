from datetime import timedelta
from logging import getLogger

from django.contrib.auth.models import User
from django.db import models, IntegrityError
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey
from xmodule.modulestore.django import modulestore

from openedx.core.djangoapps.course_groups.models import CourseUserGroup, CourseKeyField

log = getLogger(__name__)


class CourseShiftGroup(models.Model):
    """
    Represents group of users with shifted due dates.
    It is based on CourseUserGroup. To ensure that
    every user is enrolled to the one shift only
    CourseShiftMembership is used (just like for Cohorts).

    Don't use this model's methods directly, they should be used by
    other models only.
    """
    course_user_group = models.OneToOneField(CourseUserGroup)
    start_date = models.DateField(
        default=timezone.now,
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
        if not isinstance(course_key, CourseKey):
            raise TypeError("course_key must be CourseKey, not {}".format(type(course_key)))
        return cls.objects.filter(course_user_group__course_id=course_key).order_by('-start_date')

    @classmethod
    def create(cls, name, course_key, start_date=None, days_shift=None):
        """Creates new CourseShiftGroup"""
        course_user_group, created = CourseUserGroup.create(name=name, course_id=course_key)
        kwargs = {"course_user_group": course_user_group}
        if start_date:
            kwargs["start_date"] = start_date
        if days_shift:
            kwargs["days_shift"] = days_shift
        course_shift_group, created_shift = CourseShiftGroup.objects.get_or_create(**kwargs)
        return course_shift_group, created and created_shift

    def __unicode__(self):
        return u"'{}' in '{}'".format(self.name, str(self.course_key))


class CourseShiftGroupMembership(models.Model):
    """
    Represents membership in CourseShiftGroup. At any changes it
    updates CourseUserGroup.
    """
    user = models.OneToOneField(User)
    course_shift_group = models.ForeignKey(CourseShiftGroup)

    class ChangeForbidden(Exception):
        """We want to forbid update but allow deletion on rows"""
        pass

    def save(self, *args, **kwargs):
        if self.pk:
            raise self.ChangeForbidden("CourseShiftGroupMembership can't be changed, only deleted")
        save = super(CourseShiftGroupMembership, self).save(*args, **kwargs)
        if self.user not in self.course_shift_group.users.all():
            self._add_user_with_membership(self.course_shift_group, self.user)
        return save

    def delete(self, *args, **kwargs):
        delete = super(CourseShiftGroupMembership, self).delete(*args, **kwargs)
        self._delete_user_without_membership(self.user, self.course_shift_group)
        return delete

    @classmethod
    def transfer_user(cls, user, course_shift_group_from, course_shift_group_to):
        """
        Transfers user from one shift to another one. If the first one is None,
        user is enrolled to the 'course_shift_group_to'. If the last one
        is None, user is unenrolled from shift 'course_shift_group_from'
        """

        if course_shift_group_from and user not in course_shift_group_from.users.all():
            raise ValueError("User {} is not in {}".format(user.username, course_shift_group_from.name))
        if course_shift_group_from:
            membership = cls.objects.get(user=user)
            if course_shift_group_from == course_shift_group_to:
                return membership
            membership.delete()
        if course_shift_group_to:
            return cls.objects.create(user=user, course_shift_group=course_shift_group_to)

    @classmethod
    def _add_user_with_membership(cls, course_shift_group, user):
        """Adds users only when they are already have shift membership"""
        try:
            membership = CourseShiftGroupMembership.objects.get(user=user)
        except CourseShiftGroupMembership.DoesNotExist:
            raise IntegrityError("Membership for user {} not found".format(user.username))
        if membership.course_shift_group != course_shift_group:
            raise IntegrityError("Found membership for user {}, supposed to be {}".format(
                membership.course_shift_group.name,
                course_shift_group.name
            ))
        if not user in course_shift_group.users.all():
            course_shift_group.course_user_group.users.add(user)

    @classmethod
    def _delete_user_without_membership(cls, user, course_shift_group):
        """Deletes user from course_shift_group if he doesn't have membership."""
        try:
            membership = CourseShiftGroupMembership.objects.get(user=user)
        except CourseShiftGroupMembership.DoesNotExist:
            membership = None
        if membership:
            raise IntegrityError("Found membership for user {}, supposed to be None".format(
                user.username,
                membership.name
            ))
        course_shift_group.course_user_group.users.remove(user)

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

    def __init__(self, *args, **kwargs):
        super(CourseShiftSettings, self).__init__(*args, **kwargs)
        # This attribute is used to clear all course shift plans when
        # feature is turned off in course
        self._original_is_shift_enabled = self.is_shift_enabled

    @property
    def last_start_date(self):
        shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        if not shifts:
            return self.course_start_date
        return shifts[0].start_date

    @property
    def course_start_date(self):
        course = modulestore().get_course(self.course_key)
        return course.start

    @classmethod
    def update_course_shift_groups(cls, course_key):
        "Generate course shift group if necessary according to the settings"
        current_settings, created = cls.objects.get_or_create(course_key=course_key)
        if not current_settings.is_shift_enabled:
            return

        plan = None
        if current_settings.is_autostart:
            last_date = current_settings.last_start_date
            next_start_date = last_date + timedelta(days=current_settings._autostart_period_days)
        else:
            course_shifts_plans = current_settings.plans.all().order_by('start_date')
            if not course_shifts_plans:
                return
            plan = course_shifts_plans[0]
            next_start_date = plan.start_date

        if next_start_date < timezone.now():
            days_add = int((next_start_date - current_settings.course_start_date).days)
            name = cls.naming(course_key, next_start_date)
            group, create = CourseShiftGroup.create(
                course_key=course_key,
                name=name,
                days_shift=days_add,
                start_date=next_start_date
            )
            if plan:
                plan.delete()
            return group

    @classmethod
    def naming(cls, course_key, date):
        return "shift_{}_{}".format(str(course_key), str(date))

    def save(self, *args, **kwargs):
        if (not self.is_shift_enabled) and self._original_is_shift_enabled:
            CourseShiftPlannedRun.clear_course_shift_plans(self.course_key)
        return super(CourseShiftSettings, self).save(*args, **kwargs)

    @classmethod
    def get_course_settings(cls, course_key):
        current_settings, created = cls.objects.get_or_create(course_key=course_key)
        return current_settings


class CourseShiftPlannedRun(models.Model):
    """
    Represents planned shift for course. Used
    only when course shift dates are set up manually(not 'is_autostart')
    """
    course_shift_settings = models.ForeignKey(
        CourseShiftSettings,
        related_name="plans")
    start_date = models.DateField(default=timezone.now)

    @classmethod
    def clear_course_shift_plans(cls, course_key):
        plans = cls.objects.filter(course_shift_settings__course_key=course_key)
        for x in plans:
            x.delete()
