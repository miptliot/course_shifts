Description
-----------
This is django app based on OpenEdx Ficus release `"open-release/ficus.2"
<https://github.com/edx/edx-platform/tree/open-release/ficus.2>`_
that should provide the way for student to move forward all due dates for given course according to the rules defined by the course staff.
Similar feature at the Coursera is called "Session Switch": when activated, course has several sessions with the same content but different deadlines and student can switch them at will. This feature can be useful when student have missed some deadlines but still wants to
finish the course and get credit.

There are several differences between this app and course rerun/CCX:

1. The content of the course is the same in all course shifts. Therefore it should be easier for staff to upgrade such course if necessary. It also doesn't spend additional system resources.

2. Forum is shared between all course shifts. This can be useful when there are not so much students in each shift.

3. Students can use this function when they want, and therefore course schedule becomes more flexible.

Details
-------
Feature is implemented via additional FieldOverrideProvider and CourseUserGroups, similar to the way it's done for 'INDIVIDUAL_DUE_DATES' feature.
Every course student is associated with some CourseUserGroup, and provider checks for membership and shifts due dates accordingly.

Installation
------------

1. 'course_shifts' should be added to the INSTALLED_APPS variable, feature should be enabled:

::

  INSTALLED_APPS += ('openedx.core.djangoapps.course_shifts',)
  FEATURES["ENABLE_COURSE_SHIFTS"] = True

2. course_shifts.provider.CourseShiftOverrideProvider should be added to the FIELD_OVERRIDE_PROVIDERS

::

  FIELD_OVERRIDE_PROVIDERS += (
      'openedx.core.djangoapps.course_shifts.provider.CourseShiftOverrideProvider',
  )

Note that if feature INDIVIDUAL_DUE_DATES is also used, than IndividualStudentOverrideProvider must be added before CourseShiftOverrideProvider.

3. Run course_shifts migrations

::

  python manage.py lms migrate course_shifts --settings=YOUR_SETTINGS


4. Pull `this
<https://github.com/zimka/edx-platform-1/tree/course_shifts>`_
branch from github. Branch is based on edx release 'open-release/ficus.2'. It contains all necessary changes in edx-platform.
