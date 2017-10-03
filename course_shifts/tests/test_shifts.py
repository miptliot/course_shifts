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
from ..models import CourseShiftGroup, CourseShiftGroupMembership, CourseUserGroup, CourseShiftSettings
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


class EnrollClsFields(object):
    _ENROLL_BEFORE = 7
    _ENROLL_AFTER = 0
    _PERIOD = 20
    _COURSE_DATE_START = 14


@attr(shard=2)
class TestCourseShiftSettings(ModuleStoreTestCase, EnrollClsFields):
    """
    Test the course shifts settings
    """
    MODULESTORE = TEST_DATA_MIXED_MODULESTORE

    def setUp(self):
        """
        Make sure that course is reloaded every time--clear out the modulestore.
        """
        super(TestCourseShiftSettings, self).setUp()
        date = datetime.datetime.now() - datetime.timedelta(days=self._COURSE_DATE_START)
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id
        self._no_groups_check()

    def tearDown(self):
        self._delete_groups()

    def _settings_setup(self, period=None, autostart=False):
        """
        Not included into setUp because should be tests
        """
        if not period:
            period = self._PERIOD
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        settings.is_shift_enabled = True
        settings.enroll_before_days = self._ENROLL_BEFORE
        settings.enroll_after_days = self._ENROLL_AFTER
        settings.is_autostart = autostart
        settings.autostart_period_days = period
        settings.save()
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        self.assertTrue(settings.enroll_before_days == self._ENROLL_BEFORE)
        self.assertTrue(settings.enroll_after_days == self._ENROLL_AFTER)
        return

    def _delete_groups(self):
        shift_groups = CourseShiftGroup.objects.all()
        for x in shift_groups:
            x.delete()

    def _number_of_shifts(self, custom_period):
        """
        Calculates how many shifts should be according
        to the current settings
        """
        course_started_days_ago = self._COURSE_DATE_START
        # enroll_before effectively shifts start date here
        # E.g. course started 15.01, period is 10, enroll_before is 5
        # First shift is created immediately,second is created at 20.01,
        # next one is created at 30.01.

        course_started_days_ago += self._ENROLL_BEFORE
        shifts_number = int(course_started_days_ago / custom_period)
        shifts_number += 1
        return shifts_number

    def _no_groups_check(self):
        """
        Checks that there is no groups.
        Used at start and anywhere needed
        """
        shift_groups = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(
            len(shift_groups) == 0,
            "Course has shift groups at start:{}".format(shift_groups)
        )

    def test_settings_generation_and_saving(self):
        """
        Tests that settings got by get_course_settings saved correctly
        """
        self._settings_setup(autostart=False)
        settings = CourseShiftSettings.get_course_settings(self.course_key)

        self.assertTrue(settings.is_shift_enabled == True)
        self.assertTrue(settings.is_autostart == False)
        self.assertTrue(settings.autostart_period_days == self._PERIOD)

    def test_autostart_generation_one(self):
        """
        Single start should be generated - default shift at start
        """
        custom_period = 30
        self._settings_setup(period=custom_period, autostart=True)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        shifts_number = self._number_of_shifts(custom_period)
        self.assertTrue(len(course_shifts) == shifts_number, "Must be {} shift, found: {}".format(shifts_number, str(course_shifts)))

    def test_autostart_generation_two(self):
        """
        Two shifts must be generated automatically, default and one more
        """
        custom_period = 12
        self._settings_setup(period=custom_period, autostart=True)
        shifts_number = self._number_of_shifts(custom_period)
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == shifts_number, "Must be {} shifts, found:{}".format(
            shifts_number,
            str(course_shifts)))

    def test_autostart_generation_three(self):
        """
        Three shifts must be generated automatically
        """
        self._no_groups_check()
        custom_period = 8
        self._settings_setup(period=custom_period, autostart=True)
        shifts_number = self._number_of_shifts(custom_period)
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        course_shifts = CourseShiftGroup.get_course_shifts(self.course_key)
        self.assertTrue(len(course_shifts) == shifts_number, "Must be {} shifts, found:{}".format(
            shifts_number,
            str(course_shifts)))

    def test_turn_off_autostart(self):
        """
        Checks that when autostart is turned off
        shifts aren't created
        """
        self._no_groups_check()
        self._settings_setup(autostart=False, period=8)
        self._no_groups_check()
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        self._no_groups_check()


@attr(shard=2)
class TestCourseShiftManager(ModuleStoreTestCase, EnrollClsFields):

    def setUp(self):
        super(TestCourseShiftManager, self).setUp()
        date = datetime.datetime.now() - datetime.timedelta(days=14)
        self.course = ToyCourseFactory.create(start=date)
        self.course_key = self.course.id
        self.shift_settings = CourseShiftSettings.get_course_settings(self.course_key)
        self.shift_settings.is_shift_enabled = True
        self.shift_settings.is_autostart = False
        self.shift_settings.save()
        self.user = UserFactory(username="test", email="a@b.com")
        self._no_groups_check()

    def tearDown(self):
        self._delete_groups()

    def _settings_setup(self, period=None, autostart=False):
        """
        Not included into setUp because should be tests
        """
        if not period:
            period = self._PERIOD
        settings = CourseShiftSettings.get_course_settings(self.course_key)
        settings.is_shift_enabled = True
        settings.enroll_before_days = self._ENROLL_BEFORE
        settings.enroll_after_days = self._ENROLL_AFTER
        settings.is_autostart = autostart
        settings.autostart_period_days = period
        settings.save()
        return

    def _delete_groups(self):
        for x in CourseShiftGroup.objects.all():
            x.delete()

    def _no_groups_check(self):
        """
        Checks that there is no groups.
        Used at start and anywhere needed
        """
        shift_groups = CourseShiftGroup.get_course_shifts(self.course_key)
        correct = len(shift_groups) == 0
        message = str(shift_groups)
        if not correct:
            self._delete_groups()
        self.assertTrue(
            correct,
            message
        )

    def test_get_user_course_shift(self):
        """
        Tests method get_user_course_shift
        """
        self._settings_setup()
        user = self.user
        shift_manager = CourseShiftManager(course_key=self.course_key)
        shift_group = shift_manager.get_user_shift(user)
        self.assertFalse(shift_group, "User shift group is {}, should be None".format(str(shift_group)))

        test_a_shift_group, created = CourseShiftGroup.create("test_shift_group_t1", self.course_key)
        CourseShiftGroupMembership.transfer_user(user, None, test_a_shift_group)
        shift_group = shift_manager.get_user_shift(user)
        self.assertTrue(shift_group==test_a_shift_group, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(test_a_shift_group)
        ))
        self._delete_groups()
        self._no_groups_check()

    def test_get_user_course_shift_disabled(self):
        self._settings_setup()
        user = self.user
        test_a_shift_group, created = CourseShiftGroup.create("test_shift_group_t2", self.course_key)
        CourseShiftGroupMembership.transfer_user(user, None, test_a_shift_group)

        self.shift_settings.is_shift_enabled = False
        self.shift_settings.save()
        shift_manager = CourseShiftManager(self.course_key)
        shift_group = shift_manager.get_user_shift(user)
        self.assertTrue(shift_group is None, "User shift group is {}, should be None".format(str(shift_group)))

        self.shift_settings.is_shift_enabled = True

    def test_get_active_shifts(self):
        """
        Tests method get_active_shifts without user
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)

        group1, created = CourseShiftGroup.create("test_group", self.course_key)
        group2, created = CourseShiftGroup.create("test_group2", self.course_key, start_date=date_shifted(days=5))

        course_shifts = shift_manager.get_active_shifts()
        correct = (group1 in course_shifts) and (group2 in course_shifts) and (len(course_shifts) == 2)
        self.assertTrue(correct, "Shifts should be {} and {}, found {}".format(
            str(group1),
            str(group2),
            str(course_shifts)
        ))

    def test_create_shift(self):
        """
        Tests manager.create_shift
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        test_group = shift_manager.create_shift()
        groups = shift_manager.get_all_shifts()
        correct = test_group in groups and len(groups) == 1
        self.assertTrue(correct, "Should be only {}, found: {}".format(
            str(test_group),
            str(groups)
        ))

        test_group_same = shift_manager.create_shift()
        groups = shift_manager.get_all_shifts()
        correct = test_group_same in groups and len(groups) == 1
        self.assertTrue(correct, "Should be only {}, found: {}".format(
            str(test_group),
            str(groups)
        ))
        self.assertTrue(test_group_same==test_group, "Groups different: {} and {}".format(
            str(test_group),
            str(test_group_same)
        ))

        test_group_other = shift_manager.create_shift(date_shifted(1))
        groups = shift_manager.get_all_shifts()
        correct = test_group_same in groups \
            and test_group_other in groups \
            and len(groups) == 2
        self.assertTrue(correct, "Should be {} and {}, found: {}".format(
            str(test_group),
            str(test_group_other),
            str(groups)
        ))

    def test_create_shift_different_name_error(self):
        """
        Checks error at shift creation with same date
        but different name
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        test_group = shift_manager.create_shift()
        with self.assertRaises(IntegrityError):
            test_group_error = shift_manager.create_shift(name="same_date_different_name")

    def test_create_shift_different_date_error(self):
        """
        Checks error at shift creation with same name
        but different date.
        Checks that for same name and same date error not raised
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)

        test_group = shift_manager.create_shift()
        name = test_group.name
        with self.assertRaises(IntegrityError):
            test_group_error = shift_manager.create_shift(name=name, start_date=date_shifted(1))

        test_group2 = shift_manager.create_shift()
        self.assertTrue(test_group==test_group2, "Different groups: {} {}".format(
            str(test_group),
            str(test_group2)
        ))
        self._delete_groups()
        self._no_groups_check()

    def test_get_active_groups(self):
        """
        Checks get_active_groups without user
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        self._no_groups_check()
        group = shift_manager.create_shift(date_shifted(-20))
        active_groups = shift_manager.get_active_shifts()
        self.assertTrue(len(active_groups) == 0, "Should be empty, found {}".format(str(active_groups)))

        group2 = shift_manager.create_shift(date_shifted(1))
        active_groups = shift_manager.get_active_shifts()
        correct = len(active_groups) == 1 and group2 in active_groups
        self.assertTrue(correct, "Should be {}, found {}".format(
            str(group2),
            str(active_groups)
        ))
        self._delete_groups()
        self._no_groups_check()

    def test_get_active_groups_user(self):
        """
        Checks get_active_groups with user.
        Old groups are inactive but if has membership, later groups are active
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        group = shift_manager.create_shift(date_shifted(-20))
        group2 = shift_manager.create_shift(date_shifted(-30))

        active_user_groups = shift_manager.get_active_shifts(self.user)
        correct = len(active_user_groups) == 0
        self.assertTrue(correct, "Active user groups: {}".format(
            str(active_user_groups)
        ))

        CourseShiftGroupMembership.transfer_user(self.user, None, group2)
        active_user_groups = shift_manager.get_active_shifts(self.user)
        correct = len(active_user_groups) == 1 and group in active_user_groups
        self.assertTrue(correct, "Active user groups: {}".format(
            str(active_user_groups)
        ))
        self._delete_groups()
        self._no_groups_check()

    def test_get_active_groups_future(self):
        """
        Checks that future groups are inactive
        without user and with user that has older
        membership
        """
        self._settings_setup()
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        group = shift_manager.create_shift(start_date=date_shifted(-1))
        CourseShiftGroupMembership.transfer_user(self.user, None, group)

        group_future = shift_manager.create_shift(start_date=date_shifted(14))

        self.assertTrue(group_future.start_date == date_shifted(14),
                        "Start date is {}, must be {}".format(
                            str(group_future.start_date),
                            str(date_shifted(14))
        ))
        active_groups = shift_manager.get_active_shifts()
        active_user_groups = shift_manager.get_active_shifts(self.user)

        correct = len(active_user_groups) == 0 and len(active_user_groups) == 0
        self.assertTrue(correct, "Active groups: {}; \nActive user groups: {}".format(
            str(active_groups),
            str(active_user_groups)
        ))
        self._delete_groups()
        self._no_groups_check()

    def test_enroll_user(self):
        """
        Tests method sign_user_on_shift.
        Valid scenarios
        """
        self._no_groups_check()
        user = self.user
        shift_manager = CourseShiftManager(self.course_key)

        group1 = shift_manager.create_shift()
        group2 = shift_manager.create_shift(date_shifted(days=-5))

        shift_manager.enroll_user(user, group1)
        shift_group = shift_manager.get_user_shift(user)
        self.assertTrue(shift_group == group1, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group1)
        ))

        shift_manager.enroll_user(
            user=user,
            shift=group2
        )
        shift_group = shift_manager.get_user_shift(user)
        self.assertTrue(shift_group == group2, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group2)
        ))

        shift_manager.enroll_user(user, shift=group1)
        shift_group = shift_manager.get_user_shift(user)
        self.assertTrue(shift_group == group1, "User shift group is {}, should be {}".format(
            str(shift_group),
            str(group1)
        ))
        self._delete_groups()

    def test_enroll_user_error_course_key(self):
        """
        Checks that error is raised when enroll_user
        gets shift from other course
        """
        self._no_groups_check()
        user = self.user
        shift_manager = CourseShiftManager(self.course_key)

        other_course = ToyCourseFactory.create(org="neworg")
        other_course_key = other_course.id
        other_manager = CourseShiftManager(other_course_key)
        other_manager.settings.is_shift_enabled = True
        other_manager.settings.is_autostart = False
        other_group = other_manager.create_shift()

        with self.assertRaises(ValueError):
            shift_manager.enroll_user(user, other_group)
        self._delete_groups()

    def test_enroll_user_error_inactive(self):
        """
        Checks that enroll_user raises error
        if shift is not active
        """
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        group = shift_manager.create_shift(date_shifted(-20))
        active_groups = shift_manager.get_active_shifts(self.user)
        self.assertTrue(
            not(group in active_groups),
            "Active groups : {}".format(str(active_groups))
        )
        with self.assertRaises(ValueError):
            shift_manager.enroll_user(self.user, group)
        self._delete_groups()

    def test_enroll_user_inactive_forced(self):
        """
        Checks that no error raised when enroll_user
        is used in forced mode for inactive shift
        """
        self._no_groups_check()
        shift_manager = CourseShiftManager(self.course_key)
        group = shift_manager.create_shift(date_shifted(-20))
        active_groups = shift_manager.get_active_shifts()
        self.assertTrue(
            not(group in active_groups),
            "Active groups : {}".format(str(active_groups))
        )
        shift_manager.enroll_user(self.user, group, forced=True)
        user_shift = shift_manager.get_user_shift(self.user)
        self.assertTrue(
            user_shift==group,
            "User shift:{}, should be {}".format(
                str(user_shift),
                str(group)
            )
        )

    def test_unenroll_user(self):
        """
        Tests that enroll with None leads to unenrollment
        """
        shift_manager = CourseShiftManager(self.course_key)
        group = shift_manager.create_shift(date_shifted(-5))

        shift_manager.enroll_user(self.user, None)
        current_shift = shift_manager.get_user_shift(self.user)
        self.assertTrue(
            current_shift is None,
            "Current shift should be None, but it is {}".format(str(current_shift))
        )
        shift_manager.enroll_user(self.user, group)
        shift_manager.enroll_user(self.user, None)
        self.assertTrue(
            current_shift is None,
            "Current shift should be None, but it is {}".format(str(current_shift))
        )
