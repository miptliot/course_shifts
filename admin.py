from django.contrib import admin
from models import CourseShiftGroup


class CourseShiftAdmin(admin.ModelAdmin):
    pass

admin.site.register(CourseShiftGroup, CourseShiftAdmin)
