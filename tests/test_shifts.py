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
from ..manager import CourseShiftManager

def date_shifted(days):
    return (datetime.datetime.now() + datetime.timedelta(days=days)).date()


@attr(shard=2)
class TestCourseShiftGroup(ModuleStoreTestCase):
    """
    Test the course shifts feature
    """
    MODULESTORE = TEST_DATA_MIXED_MODULESTORE

    def setUp(self):
        """
        Make sure that course is reloaded every time--clear out the modulestore.
        """
        super(TestCourseShiftGroup, self).setUp()
        date = datetime.datetime.now()
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id

    def _no_groups_check(self):
        """
        Checks that there is no groups.
        Used at start and anywhere needed
        """
        groups = CourseUserGroup.objects.filter(course_id=self.course_key)
        self.assertTrue(
            len(groups) == 0,
            "Course has user groups at start"
        )
        shift_groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(shift_groups) == 0,
            "Course has shift groups at start"
        )

    def _delete_all_shifts(self, key=None):
        if not key:
            key = self.course_key
        shift_groups = CourseShiftGroup.get_course_shifts(key)
        for x in shift_groups:
            x.delete()

    def test_creates_cug(self):
        """
        Checks that CourseUserGroup is created when CSG created
        """
        self._no_groups_check()

        name = "test_shift_group"
        test_shift_group, created = CourseShiftGroup.create(name, self.course_key)

        groups = CourseUserGroup.objects.filter(course_id=self.course_key)
        correct = len(groups) == 1 and groups.first().name == name
        self.assertTrue(correct, "Should be only 'test_shift_group' user group, found:{}".format(
            str([x.name for x in groups])
        ))

        shift_groups = CourseShiftGroup.get_course_shifts(self.course_key)
        correct = len(shift_groups) == 1 and test_shift_group in shift_groups
        self.assertTrue(
            correct,
            "Should be only {}, found:{}".format(
                str(test_shift_group),
                str(shift_groups)
        ))

        self._delete_all_shifts()

    def test_deletes_cug(self):
        """
        Checks that CourseUserGroup us deleted hen CSG deleted
        """
        self._no_groups_check()
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        test_shift_group.delete()
        self._no_groups_check()

    def test_deleted_by_cug_delete(self):
        """
        Checks that CourseShiftGroup is deleted when CourseUserGroup is deleted
        """
        self._no_groups_check()
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        test_shift_group.course_user_group.delete()
        self._no_groups_check()

    def test_create_same_course_and_date_error(self):
        """
        Checks that error raised for CSG creation with same course_key and
        start_date, BUT DIFFERENT name
        """
        self._no_groups_check()
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)

        with self.assertRaises(IntegrityError) as context_manager:
            test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key)
        self._delete_all_shifts()

    def test_create_same_course_dif_date_ok(self):
        """
        Checks that error NOT raised for CSG creation with same course_key
        but different date
        """
        self._no_groups_check()
        test_shift_group, created = CourseShiftGroup.create("test_shift_group", self.course_key)
        test_shift_group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key,
                                                             start_date=date_shifted(1))
        groups = CourseShiftGroup.get_course_shifts(self.course_key)
        correct = test_shift_group2 in groups and \
            test_shift_group in groups and \
            len(groups) == 2

        self.assertTrue(correct, "Should be test_shift_group and test_shift_group2, found:{}".format(
            str(groups)
        ))
        self._delete_all_shifts()

    def test_create_same_course_and_date_copy(self):
        """
        Checks that copy returned for CSG creation with same course_key and
        start_date, AND SAME name
        """
        self._no_groups_check()
        name = "test_shift_group"
        test_shift_group, created = CourseShiftGroup.create(name, self.course_key)
        test_shift_group2, created2 = CourseShiftGroup.create(name, self.course_key)

        self.assertFalse(created2, "shift groups should be same: {}".format(
            str(test_shift_group),
            str(test_shift_group2)
        ))
        self._delete_all_shifts()

    def test_same_name_different_date_error(self):
        """
        Checks that error raised for CSG creation with same course_key and name,
        but different start_date
        """
        self._no_groups_check()
        name = "test_shift_group"
        test_shift_group, created = CourseShiftGroup.create(name, self.course_key)
        with self.assertRaises(IntegrityError) as context_manager:
            test_shift_group2, created2 = CourseShiftGroup.create(name, self.course_key, start_date=date_shifted(1))
        self._delete_all_shifts()


@attr(shard=2)
class TestCourseShiftGroupMembership(ModuleStoreTestCase):
    MODULESTORE = TEST_DATA_MIXED_MODULESTORE

    def setUp(self):
        """
        Make sure that course is reloaded every time--clear out the modulestore.
        """
        super(TestCourseShiftGroupMembership, self).setUp()
        date = datetime.datetime.now()
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id
        self.user = UserFactory(username="test", email="a@b.com")
        self.group, created = CourseShiftGroup.create("test_shift_group", self.course_key)

        self.second_course = ToyCourseFactory.create(org="neworg")
        self.second_course_key = self.second_course.id

    def _delete_all_memberships(self):
        memberships = CourseShiftGroupMembership.objects.all()
        for m in memberships:
            m.delete()

    def _check_no_memberships(self):
        mems = CourseShiftGroupMembership.objects.all()
        self.assertTrue(len(mems) == 0)

    def test_membership_creation(self):
        """
        Tests shifts transfer to group pushes user to CourseShiftGroup
        """
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        self.assertTrue(self.user in self.group.users.all())
        self._delete_all_memberships()

    def test_membership_deletion(self):
        """
        Tests membership deletion and transfer to None removes user from Group
        """
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        membership.delete()
        self.assertTrue(len(self.group.users.all()) == 0)

        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        CourseShiftGroupMembership.transfer_user(self.user, self.group, None)
        self.assertTrue(len(self.group.users.all()) == 0)

    def test_membership_course_user_unique(self):
        """
        Tests that there can't be two membership for user in same course_key
        """
        group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key,
            start_date=date_shifted(1))
        CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        with self.assertRaises(ValueError) as context_manager:
            CourseShiftGroupMembership.objects.create(user=self.user, course_shift_group=group2)
        group2.delete()
        self._delete_all_memberships()

    def test_user_membership_two_courses(self):
        """
        Tests that user can have two memberships in two different courses
        """
        group2, created = CourseShiftGroup.create("test_shift_group", self.second_course_key)
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        membership2 = CourseShiftGroupMembership.transfer_user(self.user, None, group2)
        mems = CourseShiftGroupMembership.objects.all()
        self.assertTrue(len(mems) == 2, "Must be 2 memberships, found: {}".format(
            str(mems)
        ))
        self._delete_all_memberships()

    def test_two_users_for_course_membership(self):
        """
        Tests that there can be two users in CourseShiftGroup
        """
        user2 = UserFactory(username="test2", email="a2@b.com")
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        membership = CourseShiftGroupMembership.transfer_user(user2, None, self.group)
        mems = CourseShiftGroupMembership.objects.all()
        self.assertTrue(len(mems) == 2, "Must be 2 memberships, found: {}".format(
            str(mems)
        ))
        self._delete_all_memberships()

    def test_membership_unchangable(self):
        """
        Tests that membership can't be changed
        """
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        group2, created = CourseShiftGroup.create("test_shift_group2", self.second_course_key)
        membership.course_shift_group = group2
        with self.assertRaises(ValueError):
            membership.save()
        group2.delete()
        self._delete_all_memberships()

    def test_membership_transfer_valid(self):
        """
        Tests transfer from None, to shift group from the same course, to None
        """
        self.assertTrue(len(self.group.users.all()) == 0)

        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        self.assertTrue(self.user in self.group.users.all())

        group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key, start_date=date_shifted(1))
        membership = CourseShiftGroupMembership.transfer_user(self.user, self.group, group2)
        self.assertTrue(self.user in group2.users.all())
        self.assertTrue(len(self.group.users.all()) == 0)

        membership = CourseShiftGroupMembership.transfer_user(self.user, group2, None)
        self.assertTrue(len(self.group.users.all()) == 0)
        self.assertTrue(len(group2.users.all()) == 0)
        group2.delete()

    def test_transfer_intercourse_error(self):
        """
        Tests user can't be transfered between to the shift from
        the different course
        """
        group2, created = CourseShiftGroup.create("test_shift_group2", self.second_course_key)
        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        with self.assertRaises(ValueError):
            membership = CourseShiftGroupMembership.transfer_user(self.user, self.group, group2)
        group2.delete()

    def test_transfer_from_error(self):
        """
        Tests that transfer raises error when shift_from is incorrect
        """
        group2, created = CourseShiftGroup.create("test_shift_group2", self.course_key, start_date=date_shifted(1))

        with self.assertRaises(ValueError) as context_manager:
            membership = CourseShiftGroupMembership.transfer_user(self.user, self.group, group2)
        message_list = ["User's membership is", "None", "not"]
        message_right = list(x in str(context_manager.exception) for x in message_list)
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception)))

        membership = CourseShiftGroupMembership.transfer_user(self.user, None, self.group)

        with self.assertRaises(ValueError) as context_manager:
            membership = CourseShiftGroupMembership.transfer_user(self.user, group2, None)
        message_list = ["User's membership is", "test_shift_group2", "test_shift_group", "not"]
        message_right = list(x in str(context_manager.exception) for x in message_list)
        self.assertTrue(all(message_right), "Message:{}".format(str(context_manager.exception)))

        self._delete_all_memberships()

    def test_get_user_membership(self):
        membership = CourseShiftGroupMembership.get_user_membership(self.user, self.course_key)
        self.assertIsNone(membership)

        CourseShiftGroupMembership.transfer_user(self.user, None, self.group)
        membership = CourseShiftGroupMembership.get_user_membership(self.user, self.course_key)
        self.assertTrue(membership.course_shift_group == self.group, "Membershift group:{}".format(
            str(membership.course_shift_group)
            ))


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
        self._settings_setup()
        settings = CourseShiftSettings.get_course_settings(self.course_key)

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
        mes = "Course shifts shouldn't be generated, found:{}".format(str(course_shifts))
        self.assertTrue(len(course_shifts) == 0, mes)

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
        shift_manager = CourseShiftManager(course_key=self.course_key)
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
        shift_manager = CourseShiftManager(self.course_key)
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
        shift_manager = CourseShiftManager(self.course_key)
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
        shift_manager = CourseShiftManager(course_key=self.course_key)
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

        shift_manager.sign_user_on_shift(
            user=user,
            shift_to=group2,
            shift_from=group1,
            course_key=self.course_key,
            shift_up_only=False
        )
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
        shift_manager = CourseShiftManager(course_key=self.course_key)
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
            shift_manager.sign_user_on_shift(
                user=user,
                shift_from=group1,
                shift_to=group_invalid,
                course_key=second_course_key
            )
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
