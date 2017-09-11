"""
Tests for course shifts
"""
# pylint: disable=no-member
from nose.plugins.attrib import attr
import datetime

from opaque_keys.edx.locations import SlashSeparatedCourseKey
from student.tests.factories import UserFactory, RegistrationFactory, UserProfileFactory
from xmodule.modulestore.tests.django_utils import TEST_DATA_MIXED_MODULESTORE, ModuleStoreTestCase
from xmodule.modulestore.tests.factories import ToyCourseFactory
from django.core.exceptions import ValidationError
from ..models import CourseShiftGroup, CourseShiftGroupMembership, CourseUserGroup


def date_shifted(shift):
    return (datetime.datetime.now() + datetime.timedelta(days=shift)).date()


@attr(shard=2)
class TestCourseShifts(ModuleStoreTestCase):
    """
    Test the course shifts feature
    """
    MODULESTORE = TEST_DATA_MIXED_MODULESTORE

    def setUp(self):
        """
        Make sure that course is reloaded every time--clear out the modulestore.
        """
        super(TestCourseShifts, self).setUp()
        date = datetime.datetime.now()
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id

    def date_shifted(self, shift):
        return (datetime.datetime.now() + datetime.timedelta(days=shift)).date()

    def test_shift_group_creation(self):
        """
        Tests shifts groups creation and .get_course_shifts method.
        Valid scenarios.
        """
        groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(groups) == 0,
            "Course has shift groups at creation"
        )

        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(groups) == 1,
            "Course has {} shifts, must have 1".format(len(groups))
        )
        self.assertTrue(
            test_shift_group in groups,
            "Created group is not in course shifts:'{}' not in '{}'".format(
                str(test_shift_group),(str(groups))
            )
        )

        test_shift_group.delete()
        groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(groups) == 0,
            "Course has shift groups after group deletion"
        )

    def test_shift_group_deletion(self):
        """
        Tests shifts groups deletion and .get_course_shifts method.
        Valid scenarios.
        """

        # create shift, check user
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        course_user_groups = CourseUserGroup.objects.all()
        self.assertTrue(
            len(course_user_groups) == 1,
            "Group was not created: {}".format(str(course_user_groups))
        )

        # delete user, check shift
        test_shift_group.course_user_group.delete()
        course_shift_groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(course_shift_groups) == 0,
            "More than zero course shift groups after deletion: {}".format(str(course_shift_groups))
        )

        # create shift, delete shift, check user
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        test_shift_group.delete()
        course_user_groups = CourseUserGroup.objects.all()
        self.assertTrue(
            len(course_user_groups) == 0,
            "Group was not deleted: {}".format(str(course_user_groups))
        )

    def test_shift_creation_errors(self):
        """
        Tests behavior of CourseShiftGroup.create in case of
        incorrect course_key, name conflict
        """
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)

        with self.assertRaises(ValidationError) as context_manager:
            test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key)
        exception_msg_parts = ("Shift for course", "with date", "already exists")
        self.assertTrue(all(x in str(context_manager.exception) for x in exception_msg_parts))

        # when try to create group shift with same (name, key, date) already exists we get that old shift
        test_shift_group_same, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        self.assertFalse(created)
        self.assertTrue(test_shift_group.pk == test_shift_group_same.pk)
        test_shift_group.delete()

    def test_membership_creation(self):
        """
        Tests shifts membership creation and deletion.
        Valid scenarios only.
        """
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        user = UserFactory(username="test", email="a@b.com")

        CourseShiftGroupMembership.transfer_user(user, None, test_shift_group)
        self.assertTrue(user in test_shift_group.users.all())

        CourseShiftGroupMembership.transfer_user(user, test_shift_group, None)
        self.assertTrue(len(test_shift_group.users.all()) == 0)

        date = datetime.datetime.now() + datetime.timedelta(days=7)
        test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key, start_date=date)
        CourseShiftGroupMembership.transfer_user(user, None, test_shift_group2)
        CourseShiftGroupMembership.transfer_user(user, test_shift_group2, test_shift_group)

        self.assertTrue(
            (user in test_shift_group.users.all()),
            "User wasn't transfered:{}".format(str(CourseShiftGroupMembership.objects.all()))
        )
        self.assertTrue(
            (len(test_shift_group2.users.all())==0),
            "test_shift_group2 is not empty:{}".format(str(test_shift_group2.users.all()))
        )
        test_shift_group.delete()
        test_shift_group2.delete()

    def test_membership_errors(self):
        """
        Tests transfer_user method versus wrong shift groups
        """
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key,
                                                             start_date=date_shifted(shift=10))

        user = UserFactory(username="test", email="a@b.com")
        # user doesn't have shift, but transfer from test_shift_group
        with self.assertRaises(ValueError) as context_manager:
            CourseShiftGroupMembership.transfer_user(user, test_shift_group, test_shift_group2)
        message_right = list(x in str(context_manager.exception) for x in ["User's membership is", "test_shift_group", "not"])
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception), message_right))

        # user doesn't have shift, but transfer from None
        with self.assertRaises(ValueError) as context_manager:
            CourseShiftGroupMembership.transfer_user(user, test_shift_group, None)
        message_right = list(x in str(context_manager.exception) for x in ["User's membership is", "None", "not"])
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception), message_right))

        CourseShiftGroupMembership.transfer_user(user, None, test_shift_group)

        # user has shift test_shift_group, but transfer from test_shift_group2
        with self.assertRaises(ValueError) as context_manager:
            CourseShiftGroupMembership.transfer_user(user, test_shift_group2, test_shift_group)
        message_right = list(x in str(context_manager.exception) for x in ["User's membership is", "test_shift_group", "not"])
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception), message_right))

        fake_key = SlashSeparatedCourseKey('a', 'b', 'c')
        fake_shift_group, created = CourseShiftGroup.create("fake_shift_group", fake_key)

        # transfer from one course to other
        with self.assertRaises(ValueError) as context_manager:
            CourseShiftGroupMembership.transfer_user(user, test_shift_group, fake_shift_group)
        message_right = list(x in str(context_manager.exception) for x in ["Course groups have different course_key"])
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception), message_right))

        test_shift_group.delete()
        test_shift_group2.delete()
        fake_shift_group.delete()
