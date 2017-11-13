# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import course_shifts.models
from django.conf import settings
import django.core.validators
import xmodule_django.models


class Migration(migrations.Migration):

    dependencies = [
        ('course_groups', '0002_auto_20171110_0815'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CourseShiftGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('course_key', xmodule_django.models.CourseKeyField(help_text=b'Which course is this group associated with', max_length=255, db_index=True)),
                ('start_date', models.DateField(default=course_shifts.models.date_now, help_text=b'Date when this shift starts')),
                ('days_shift', models.IntegerField(default=0, help_text=b"Days to add to the block's due")),
                ('course_user_group', models.OneToOneField(to='course_groups.CourseUserGroup')),
            ],
        ),
        migrations.CreateModel(
            name='CourseShiftGroupMembership',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('course_shift_group', models.ForeignKey(to='course_shifts.CourseShiftGroup')),
                ('user', models.ForeignKey(related_name='shift_membership', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='CourseShiftSettings',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('course_key', xmodule_django.models.CourseKeyField(unique=True, max_length=255, db_index=True)),
                ('is_shift_enabled', models.BooleanField(default=False, help_text=b'True value if this feature is enabled for the course run')),
                ('is_autostart', models.BooleanField(default=True, help_text=b'Are groups generated automatically with period or according to the m  anually set plan')),
                ('autostart_period_days', models.PositiveIntegerField(default=28, help_text=b'Number of days between new automatically generated shifts.Used only in autostart mode.', null=True, db_column=b'autostart_period_days', validators=[django.core.validators.MinValueValidator(0)])),
                ('enroll_before_days', models.PositiveIntegerField(default=14, help_text=b'Days before shift start when student can enroll already.E.g. if shift starts at 01/20/2020 and value is 5 then shift will beavailable from 01/15/2020.', validators=[django.core.validators.MinValueValidator(0)])),
                ('enroll_after_days', models.PositiveIntegerField(default=7, help_text=b'Days after shift start when student still can enroll.E.g. if shift starts at 01/20/2020 and value is 10 then shift will beavailable till 01/20/2020', validators=[django.core.validators.MinValueValidator(0)])),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='courseshiftgroup',
            unique_together=set([('course_key', 'start_date')]),
        ),
    ]
