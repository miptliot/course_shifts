"""
This file contains the logic for course shifts.
"""
from logging import getLogger

from datetime import timedelta
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, IntegrityError
from django.utils import timezone
from opaque_keys.edx.keys import CourseKey
from openedx.core.djangoapps.course_groups.models import CourseUserGroup, CourseKeyField
from xmodule.modulestore.django import modulestore

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

    @property
    def settings(self):
        if not hasattr(self, '_shift_settings'):
            self._shift_settings = CourseShiftSettings.get_course_settings(self.course_key)
        return self._shift_settings

    @settings.setter
    def settings(self, value):
        self._shift_settings = value

    def set_name(self, value):
        if self.name == value:
            return
        same_name_shifts = CourseShiftGroup.objects.filter(course_key=self.course_key, course_user_group__name=value)
        if same_name_shifts.first():
            raise ValueError("Shift with name {} already exists for {}".format(value, str(self.course_key)))
        self.course_user_group.name = value
        self.course_user_group.save()

    def set_start_date(self, value):
        if self.start_date == value:
            return
        same_start_date_shifts = CourseShiftGroup.objects.filter(course_key=self.course_key, start_date=value)
        if same_start_date_shifts.first():
            raise ValueError("Shift with start date {} already exists for {}".format(str(value), str(self.course_key)))
        delta_days = (value - self.start_date).days
        self.days_shift += delta_days
        self.start_date = value
        self.save()

    def get_shifted_date(self, user, date):
        """
        Returns shifted due or start date according to
        the settings
        """
        if user not in self.users.all():
            raise ValueError("User '{}' is not in shift '{}'".format(
                user.username,
                str(self)
            ))
        return date + timedelta(days=self.days_shift)

    def get_enrollment_limits(self, shift_settings=None):
        """
        Return tuple of enrollment start and end dates
        """
        if not shift_settings:
            shift_settings = self._shift_settings

        return (
            self.start_date - timedelta(days=shift_settings.enroll_before_days),
            self.start_date + timedelta(days=shift_settings.enroll_after_days)
        )

    def is_enrollable_now(self, shift_settings=None):
        if not shift_settings:
            shift_settings = self.settings
        date_start, date_end = self.get_enrollment_limits(shift_settings)
        if date_start < date_now() < date_end:
            return True
        return False

    @classmethod
    def get_course_shifts(cls, course_key):
        """
        Returns all shifts groups for given course
        """
        if not isinstance(course_key, CourseKey):
            raise TypeError("course_key must be CourseKey, not {}".format(type(course_key)))
        return cls.objects.filter(course_key=course_key).order_by('-start_date')

    @classmethod
    def get_shift(cls, course_key, name):
        """
        Returns shift for given course with given name if exists
        """
        if not isinstance(course_key, CourseKey):
            raise TypeError("course_key must be CourseKey, not {}".format(type(course_key)))
        try:
            return cls.objects.get(course_key=course_key, course_user_group__name=name)
        except:
            return None

    @classmethod
    def create(cls, name, course_key, start_date=None, days_shift=None):
        """
        Creates new CourseShiftGroup.
        If shift with (name, course_key) combination already exists returns this shift
        """
        course_user_group, created_group = CourseUserGroup.create(name=name, course_id=course_key)
        if not created_group:
            shift = CourseShiftGroup.objects.get(course_user_group=course_user_group)
            if shift.name != name:
                raise ValueError("Shift already exists with different name: {}".format(str(shift.name)))
            if shift.start_date != start_date:
                raise ValueError("Shift already exists with different start_date: {}".format(str(shift.start_date)))
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

    autostart_period_days = models.PositiveIntegerField(
        default=28,
        db_column='autostart_period_days',
        help_text="Number of days between new automatically generated shifts." \
                  "Used only in autostart mode.",
        null=True,
        validators=[MinValueValidator(0)]
    )

    enroll_before_days = models.PositiveIntegerField(
        default=14,
        help_text="Days before shift start when student can enroll already." \
                  "E.g. if shift starts at 01/20/2020 and value is 5 then shift will be" \
                  "available from 01/15/2020.",
        validators=[MinValueValidator(0)]
    )

    enroll_after_days = models.PositiveIntegerField(
        default=7,
        help_text="Days after shift start when student still can enroll." \
                  "E.g. if shift starts at 01/20/2020 and value is 10 then shift will be" \
                  "available till 01/20/2020",
        validators=[MinValueValidator(0)]
    )

    def __init__(self, *args, **kwargs):
        super(CourseShiftSettings, self).__init__(*args, **kwargs)

    @property
    def last_start_date(self):
        """
        Date when the last shift was started.
        """
        shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        if not shifts:
            return None
        return shifts[0].start_date

    @property
    def course_start_date(self):
        course = modulestore().get_course(self.course_key)
        return course.start.date()

    @classmethod
    def get_course_settings(cls, course_key):
        """
        Return shift settings for given course. Creates
        if doesn't exist
        """
        current_settings, created = cls.objects.get_or_create(course_key=course_key)
        if created:
            log.info("Settings for {} are created".format(
                str(course_key)
            ))
        return current_settings

    def build_default_name(self, **kwargs):
        """
        :param start_date
        Defines how should be shifts named if specific name wasn't given
        """
        date = kwargs.get("start_date")
        return "shift_{}_{}".format(str(self.course_key), str(date))

    def calculate_days_shift(self, start_date):
        """
        For given shift start date calculates days_shift value
        as a difference between course and shift start dates
        """
        return int((start_date - self.course_start_date).days)

    def get_next_autostart_date(self):
        """
        In autostart mode returns date when next shift starts
        In manual mode returns None
        """
        if not self.is_autostart:
            return
        if not self.last_start_date:
            return self.course_start_date
        return self.last_start_date + timedelta(days=self.autostart_period_days)

    def _calculate_launch_date(self, start_date):
        """
        Returns date when shift with given start date
        should be launched. Now it is created at the moment of
        enrollment start, but it can be changed in future
        """
        return start_date - timedelta(days=self.enroll_before_days)

    def update_shifts_autostart(self):
        """
        Creates new shifts if required by autostart settings
        """
        if not (self.is_autostart and self.is_shift_enabled):
            return
        start_date = self.get_next_autostart_date()
        if not start_date:
            return
        launch_date = self._calculate_launch_date(start_date)
        while launch_date < date_now():
            name = "auto_" + self.build_default_name(start_date=start_date)
            days_shift = self.calculate_days_shift(start_date=start_date)

            group, created = CourseShiftGroup.create(
                name=name,
                start_date=start_date,
                days_shift=days_shift,
                course_key=self.course_key
            )
            if created:
                log.info(
                    "Shift {} automatically created, launch date is {}; start date is {}, enroll_before is {}".format(
                        str(group),
                        str(launch_date),
                        str(start_date),
                        str(self.enroll_before_days)
                    ))
            start_date = self.get_next_autostart_date()
            launch_date = self._calculate_launch_date(start_date)

    def save(self, *args, **kwargs):
        self.update_shifts_autostart()
        return super(CourseShiftSettings, self).save(*args, **kwargs)

    def __unicode__(self):
        text = u"{}; -{}/+{} days,".format(
            unicode(self.course_key),
            unicode(self.enroll_before_days),
            unicode(self.enroll_after_days))
        if self.is_autostart:
            text += u"auto({})".format(self.autostart_period_days)
        else:
            text += u"manual"
        return text
