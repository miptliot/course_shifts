"""
Command should be used for existent students
which are already enrolled for given course to
transfer them into specific shifts.

Usage:
    ./manage.py lms --settings=SETTINGS mass_shift_transfer_csv --course_key=CID --csvfile=/path/to/file.csv
File should contain columns ['username', 'shiftname'].
"""

import csv
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from opaque_keys.edx.keys import CourseKey
from ...manager import CourseShiftManager


class Command(BaseCommand):
    help = "Command should be used for existent students which are already" \
           " enrolled for given course to transfer them into specific shifts."

    def add_arguments(self, parser):
        parser.add_argument('--course_key', help=u"Course Id where mass transfer is producing", type=str)
        parser.add_argument('--csvfile', help=u"Path of CSV file with 'username' and 'shiftname' columns", type=str)

    def handle(self, *args, **options):
        user_shift_pairs = []

        try:
            course_id = options.get('course_key')
            course_key = CourseKey.from_string(course_id)
            man = CourseShiftManager(course_key)
            if not man.is_enabled:
                raise ValueError("Shifts are not enabled for course '{}'".format(course_id))
        except Exception as e:
            raise CommandError("course_key error: '{}'. Nobody was transferred.".format(str(e)))

        try:
            csvfile = options.get('csvfile')
        except IOError as e:
            raise CommandError("csvfile IO error: '{}'. Nobody was transferred.".format(str(e)))

        with open(csvfile, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    username = row['username']
                    user = User.objects.get(username=username)
                    shift = man.get_shift(row['shiftname'])
                    if not shift:
                        raise ValueError("Shift '{}' not found".format(row['shiftname']))
                    user_shift_pairs.append((user, shift))
                except Exception as e:
                    raise CommandError("csvfile error for row '{}': '{}'. Nobody was transferred.".format(
                        str(row), str(type(e)) + " - "+  str(e)
                    ))

        for num, pair in enumerate(user_shift_pairs):
            user, shift = pair
            try:
                man.enroll_user(user, shift, forced=True)
            except Exception as e:
                message = "Error during transfer for user '{}' to shift '{}':{}".format(str(user), str(shift), str(e))
                message += "Have already transferred '{}' users.".format(num)
                raise CommandError(message)

        self.stdout.write("Successfully transferred {} users".format(len(user_shift_pairs)))
