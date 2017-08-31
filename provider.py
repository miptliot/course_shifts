from datetime import timedelta
from lms.djangoapps.courseware.field_overrides import FieldOverrideProvider
from xmodule.modulestore.django import modulestore
from .models import CourseShiftGroup


class CourseShiftOverrideProvider(FieldOverrideProvider):
    """
    A concrete implementation of
    :class:`~courseware.field_overrides.FieldOverrideProvider` which allows for
    overrides to be made on a per user basis.
    """

    COURSE_OVERRIDEN_NAMES = (
        'start',
    )
    BLOCK_OVERRIDEN_NAMES = (
        'due',
        'start'
    )
    OVERRIDEN_CATEGORIES = (
        'course',
        'sequential',
        'chapter'
    )

    def __init__(self, *args, **kwargs):
        super(CourseShiftOverrideProvider, self).__init__(*args, **kwargs)
        self.store = modulestore()

    def get(self, block, name, default):
        if block.category not in self.OVERRIDEN_CATEGORIES:
            return default
        if block.category == 'course' and name not in self.COURSE_OVERRIDEN_NAMES:
            return default
        if block.category != 'course' and name not in self.BLOCK_OVERRIDEN_NAMES:
            return default
        stored_block = self.store.get_item(block.location)
        return get_shifted_override_for_user(self.user, stored_block, name, default)

    @classmethod
    def enabled_for(cls, course):
        """This simple override provider is always enabled"""
        return True


def get_shifted_override_for_user(user, block, name, default):
    group = CourseShiftGroup.get_group(user)
    if not group:
        return default
    if name == 'due':
        try:
            shift = timedelta(days=group.days_add)
            return block.due + shift
        except:
            pass
    return default