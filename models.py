from django.contrib.auth.models import User
from django.db import models
from openedx.core.djangoapps.course_groups.models import CourseUserGroup


class CourseShiftGroup(models.Model):
    course_group = models.OneToOneField(CourseUserGroup, unique=True)
    days_add = models.IntegerField(default=0)

    @classmethod
    def get_group(cls, user):
        return CourseShiftGroupMembership.get_group(user)


class CourseShiftGroupMembership(models.Model):
    user = models.OneToOneField(User, unique=True)
    group = models.OneToOneField(CourseShiftGroup)

    @classmethod
    def get_group(cls, user):
        try:
            membership = cls.objects.get(user=user)
            return membership.group
        except cls.DoesNotExist:
            return None


def get_name(self):
    return 'CourseGroup {}'.format(self.name)

CourseUserGroup.add_to_class("__str__", get_name)