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
from django.db import IntegrityError
from ..models import CourseShiftGroup, CourseShiftGroupMembership, CourseUserGroup, CourseShiftSettings, CourseShiftPlannedRun
from ..manager import CourseShiftUserManager

def date_shifted(days):
    return (datetime.datetime.now() + datetime.timedelta(days=days)).date()


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

        with self.assertRaises(IntegrityError) as context_manager:
            test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key)

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
                                                             start_date=date_shifted(days=10))

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

    def test_several_courses_conflicts(self):
        """Tests several memberships in different courses"""
        second_course = ToyCourseFactory.create(org="neworg")
        second_course_key = second_course.id

        test_a_shift_group, created = CourseShiftGroup.create("test_A_shift_group", self.course_key)
        test_a_shift_group2, created = CourseShiftGroup.create("test_A_shift_group2", self.course_key,
                                                               start_date=date_shifted(days=10))

        test_b_shift_group, created = CourseShiftGroup.create("test_B_shift_group", second_course_key)
        test_b_shift_group2, created = CourseShiftGroup.create("test_B_shift_group2", second_course_key,
                                                               start_date=date_shifted(days=10))

        user = UserFactory(username="test", email="a@b.com")

        membership_a = CourseShiftGroupMembership.get_user_membership(user, course_key=self.course_key)
        membership_b = CourseShiftGroupMembership.get_user_membership(user, course_key=second_course_key)
        self.assertTrue(membership_a is None, "User's membership:{}, should be None".format(str(membership_a)))
        self.assertTrue(membership_b is None, "User's membership:{}, should be None".format(str(membership_b)))

        CourseShiftGroupMembership.transfer_user(user, None, test_a_shift_group)
        CourseShiftGroupMembership.transfer_user(user, None, test_b_shift_group)
        membership_a = CourseShiftGroupMembership.get_user_membership(user, course_key=self.course_key)
        membership_b = CourseShiftGroupMembership.get_user_membership(user, course_key=second_course_key)
        group_1 = membership_a and membership_a.course_shift_group
        group_2 = membership_b and membership_b.course_shift_group
        self.assertTrue(group_1 == test_a_shift_group, "User's membership {}, should be {}".format(
            str(group_1),
            str(test_a_shift_group)
        ))
        self.assertTrue(group_2 == test_b_shift_group, "User's membership {}, should be {}".format(
            str(group_1),
            str(test_b_shift_group)
        ))

        CourseShiftGroupMembership.transfer_user(user, test_a_shift_group, test_a_shift_group2)
        CourseShiftGroupMembership.transfer_user(user, test_b_shift_group, test_b_shift_group2)
        membership_a = CourseShiftGroupMembership.get_user_membership(user, course_key=self.course_key)
        membership_b = CourseShiftGroupMembership.get_user_membership(user, course_key=second_course_key)
        group_1 = membership_a and membership_a.course_shift_group
        group_2 = membership_b and membership_b.course_shift_group
        self.assertTrue(group_1 == test_a_shift_group2, "User's membership {}, should be {}".format(
            str(group_1),
            str(test_a_shift_group2)
        ))
        self.assertTrue(group_2 == test_b_shift_group2, "User's membership {}, should be {}".format(
            str(group_1),
            str(test_b_shift_group2)
        ))
        CourseShiftGroupMembership.transfer_user(user, test_a_shift_group2, None)
        CourseShiftGroupMembership.transfer_user(user, test_b_shift_group2, None)
        test_a_shift_group.delete()
        test_a_shift_group2.delete()
        test_b_shift_group.delete()
        test_b_shift_group2.delete()


@attr(shard=2)
class TestCourseShiftSettings(ModuleStoreTestCase):
    """
    Test the course shifts settings
    """
    MODULESTORE = TEST_DATA_MIXED_MODULESTORE

    def setUp(self):
        """
        Make sure that course is reloaded every time--clear out the modulestore.
        """
        super(TestCourseShiftSettings, self).setUp()
        date = datetime.datetime.now() - datetime.timedelta(days=14)
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id

    def _settings_setup(self, period=10, autostart=True):
        """
        Not included into setUp because should be tests
        """
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        settings.is_shift_enabled = True
        settings.is_autostart = autostart
        settings.autostart_period_days = period
        settings.save()
        return settings

    def test_settings_generation_and_saving(self):
        """
        Tests that settings got by get_course_settings saved correctly
        """
        settings = self._settings_setup()

        self.assertTrue(settings.is_shift_enabled == True)
        self.assertTrue(settings.is_autostart == True)
        self.assertTrue(settings.autostart_period_days == 10)
        settings.delete()

    def test_autostart_generation_single(self):
        """
        Single shift must be generated automatically
        """
        settings = self._settings_setup(period=9)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 1, "Must be single shift, found:{}".format(str(course_shifts)))
        for x in course_shifts:
            x.delete()

    def test_autostart_generation_three(self):
        """
        Three shifts must be generated automatically
        """
        settings = self._settings_setup(period=4)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 3, "Must be 3 shifts, found:{}".format(str(course_shifts)))
        for x in course_shifts:
            x.delete()

    def test_autostart_generation_zero(self):
        """
        Autostart but no shift should be generated.
        """
        settings = self._settings_setup(period=30)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "Must be 0 shifts, found: {}".format(str(course_shifts)))

    def test_plan_generation(self):
        """
        Tests that plans are generated correctly
        """
        settings = self._settings_setup(autostart=False)
        plans = CourseShiftPlannedRun.get_course_plans(self.course_key)
        self.assertTrue(len(plans) == 0, "There are shift plans at start:{}".format(str(plans)))

        settings.create_plan(date_shifted(-3))
        plans = CourseShiftPlannedRun.get_course_plans(self.course_key)
        self.assertTrue(len(plans) == 1, "Must be single plan, found:{}".format(str(plans)))
        plans[0].delete()

    def test_plan_launch(self):
        settings = self._settings_setup(autostart=False)

        plans = CourseShiftPlannedRun.get_course_plans(self.course_key)
        self.assertTrue(len(plans) == 0, "There are shift plans at start:{}".format(str(plans)))

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.create_plan(date_shifted(-3))
        next_plan = settings.get_next_plan()
        self.assertTrue(next_plan, "Plan is :{}".format(str(next_plan)))
        next_plan.launch_shift(name="doesnt_matter", days_add=7)

        plans = CourseShiftPlannedRun.get_course_plans(self.course_key)
        self.assertTrue(len(plans) == 0, "Shouldn't be any plans, found:{}".format(str(plans)))

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 1, "Must be single shift, found:{}".format(str(course_shifts)))

    def test_manual_generation_zero(self):
        """
        Tests manually preset plans.
        Test with zero planned runs
        """
        settings = self._settings_setup(autostart=False)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "Course shifts shouldn't be generated, found:{}".format(str(course_shifts)))

    def test_manual_generation_one(self):
        """
        Tests manually preset plans.
        Test with single planned run
        """
        settings = self._settings_setup(autostart=False)
        settings.create_plan(start_date=date_shifted(-2))

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 1, "Must be single shift, found:{}".format(str(course_shifts)))

    def test_manual_generation_three(self):
        """
        Tests manually preset plans.
        Test with three planned runs
        """
        settings = self._settings_setup(autostart=False)
        settings.create_plan(start_date=date_shifted(-6))
        settings.create_plan(start_date=date_shifted(-4))
        settings.create_plan(start_date=date_shifted(-2))

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 0, "There are course shifts at start:{}".format(str(course_shifts)))

        settings.update_shifts()

        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == 3, "Must be single shift, found:{}".format(str(course_shifts)))


@attr(shard=2)
class TestCourseShiftManager(ModuleStoreTestCase):
    def setUp(self):
        super(TestCourseShiftManager, self).setUp()
        date = datetime.datetime.now() - datetime.timedelta(days=14)
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id
        self.shift_settings = CourseShiftSettings.get_course_settings(self.course_key)
        self.shift_settings.is_shift_enabled = True
        self.shift_settings.save()

    def test_get_user_course_shift(self):
        """
        Tests method get_user_course_shift
        """
        user = UserFactory(username="test", email="a@b.com")
        shift_manager = CourseShiftUserManager(course_key=self.course_key)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group is None, "User shift group is {}, should be None".format(str(shift_group)))

        test_a_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        CourseShiftGroupMembership.transfer_user(user, None, test_a_shift_group)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group==test_a_shift_group, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(test_a_shift_group)
        ))

        self.shift_settings.is_shift_enabled = False
        self.shift_settings.save()
        shift_manager = CourseShiftUserManager(self.course_key)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group is None, "User shift group is {}, should be None".format(str(shift_group)))

        self.shift_settings.is_shift_enabled = True
        self.shift_settings.save()
        CourseShiftGroupMembership.transfer_user(user, test_a_shift_group, None)
        test_a_shift_group.delete()

    def test_get_active_shifts(self):
        """
        Tests method get_active_shifts
        """
        shift_manager = CourseShiftUserManager(self.course_key)
        course_shifts = shift_manager.get_active_shifts()
        self.assertTrue(len(course_shifts) == 0, "Must be zero shift groups, found:{}".format(str(course_shifts)))

        group1, created = CourseShiftGroup.create("test_group", self.course_key)
        group2, created = CourseShiftGroup.create("test_group2", self.course_key, start_date=date_shifted(days=-5))

        course_shifts = shift_manager.get_active_shifts()
        correct = (group1 in course_shifts) and (group2 in course_shifts) and (len(course_shifts) == 2)
        self.assertTrue(correct, "Shifts should be {} and {}, found {}".format(
            str(group1),
            str(group2),
            str(course_shifts)
        ))

        course_shifts = shift_manager.get_active_shifts(date_threshold=date_shifted(-2))
        correct = (group1 in course_shifts) and (len(course_shifts) == 1)
        self.assertTrue(correct, "Shifts should be {}, found {}".format(
            str(group1),
            str(course_shifts)
        ))
        group1.delete()
        group2.delete()

    def test_sign_user_on_shift_valid(self):
        """
        Tests method sign_user_on_shift.
        Valid scenarios
        """
        user = UserFactory(username="test", email="a@b.com")
        shift_manager = CourseShiftUserManager(course_key=self.course_key)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group is None, "User shift group is {}, should be None".format(str(shift_group)))

        group1, created = CourseShiftGroup.create("test_group", self.course_key)
        group2, created = CourseShiftGroup.create("test_group2", self.course_key, start_date=date_shifted(days=-5))

        shift_manager.sign_user_on_shift(user, group1, self.course_key)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group == group1, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group1)
        ))

        shift_manager.sign_user_on_shift(user, shift_to=group2, shift_from=group1, course_key=self.course_key, shift_up_only=False)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group == group2, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group2)
        ))

        shift_manager.sign_user_on_shift(user, shift_to=group1, course_key=self.course_key, forced=True)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group == group1, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group1)
        ))
        CourseShiftGroupMembership.transfer_user(user, group1, None)
        group1.delete()
        group2.delete()

    def test_sign_user_on_shift_invalid(self):
        """
        Tests method sign_user_on_shift.
        Invalid scenarios
        """
        second_course = ToyCourseFactory.create(org="neworg")
        second_course_key = second_course.id

        user = UserFactory(username="test", email="a@b.com")
        shift_manager = CourseShiftUserManager(course_key=self.course_key)
        shift_group = shift_manager.get_user_course_shift(user, self.course_key)
        self.assertTrue(shift_group is None, "User shift group is {}, should be None".format(str(shift_group)))

        group1, created = CourseShiftGroup.create("test_group", self.course_key)
        group2, created = CourseShiftGroup.create("test_group2", self.course_key, start_date=date_shifted(days=-5))

        group_invalid, created = CourseShiftGroup.create("invalid_test_group", second_course_key)

        with self.assertRaises(ValueError) as context_manager:
            shift_manager.sign_user_on_shift(user, group1, course_key=second_course_key)
        exception_msg_parts = ("Shift's course_key:", ", given course_key:")
        self.assertTrue(all(x in str(context_manager.exception) for x in exception_msg_parts))

        shift_manager.sign_user_on_shift(user, group1, course_key=self.course_key)

        with self.assertRaises(ValueError) as context_manager:
            shift_manager.sign_user_on_shift(user, shift_from=group1, shift_to=group_invalid, course_key=second_course_key)
        exception_msg_parts = ("Shift_from's  course_key:", "given course_key:")
        self.assertTrue(all(x in str(context_manager.exception) for x in exception_msg_parts))

        with self.assertRaises(ValueError) as context_manager:
            shift_manager.sign_user_on_shift(user, group2, self.course_key)
        exception_msg_parts = ("User's membership for given course is not None:",)
        self.assertTrue(all(x in str(context_manager.exception) for x in exception_msg_parts))

        membership = CourseShiftGroupMembership.get_user_membership(user, self.course_key)
        if membership:
            membership.delete()
        group1.delete()
        group2.delete()
        group_invalid.delete()
