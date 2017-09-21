from rest_framework import serializers
from openedx.core.lib.api.serializers import CourseKeyField
from .models import CourseShiftSettings


class CourseShiftSettingsSerializer(serializers.ModelSerializer):
    """
    Serializes CourseShiftSettings.
    is_shift_enabled mustn't be changed by api, therefore
    dropped from representation and is considered always to be True
    """
    course_key = CourseKeyField()
    enroll_after_days = serializers.IntegerField()
    enroll_before_days = serializers.IntegerField()
    autostart_period_days = serializers.IntegerField()
    is_autostart = serializers.BooleanField()

    class Meta:
        model = CourseShiftSettings
        fields = (
            'course_key',
            'enroll_after_days',
            'enroll_before_days',
            'autostart_period_days',
            'is_autostart',
        )

    def validate_enroll_after_days(self, value):
        message = "Enrollment days number after start can't be negative"
        if value < 0:
            raise serializers.ValidationError(message)

    def validate_enroll_before_days(self, value):
        message = "Enrollment days number before start can't be negative"
        if value < 0:
            raise serializers.ValidationError(message)

    def validate_autostart_period_days(self, value):
        message = "Autostart period must be positive"
        if value <= 0:
            raise serializers.ValidationError(message)
